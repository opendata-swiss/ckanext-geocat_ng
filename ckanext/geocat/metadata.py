# -*- coding: utf-8 -*-

from datetime import datetime
import time
from collections import defaultdict
from urlparse import urlparse
from owslib.csw import CatalogueServiceWeb
from owslib import util
import owslib.iso as iso
from ckan.lib.munge import munge_tag

import ckanext.geocat.xml_loader as loader
from ckanext.geocat.values import (
    ArrayValue,
    FirstInOrderValue,
    StringValue,
    XPathValue,
    XPathMultiValue,
    XPathSubValue
)

import logging
log = logging.getLogger(__name__)

swisstopo_to_ogdch_group_mapping = {
    'imageryBaseMapsEarthCover': ['geography', 'territory'],
    'imageryBaseMapsEarthCover_BaseMaps': ['geography', 'territory'],
    'imageryBaseMapsEarthCover_EarthCover': ['geography', 'territory'],
    'imageryBaseMapsEarthCover_Imagery': ['geography', 'territory'],
    'location': ['geography', 'territory'],
    'elevation': ['geography', 'territory'],
    'boundaries': ['geography', 'territory'],
    'planningCadastre': ['geography', 'territory'],
    'planningCadastre_Planning': ['geography', 'territory'],
    'planningCadastre_Cadastre': ['geography', 'territory'],
    'geoscientificInformation': ['geography', 'territory'],
    'geoscientificInformation_Geology': ['geography', 'territory'],
    'geoscientificInformation_Soils': ['geography', 'territory'],
    'geoscientificInformation_NaturalHazards': ['geography', 'territory'],
    'biota': ['geography', 'territory', 'agriculture'],
    'oceans': ['geography', 'territory'],
    'inlandWaters': ['geography', 'territory'],
    'climatologyMeteorologyAtmosphere': ['geography', 'territory'],
    'environment': ['geography', 'territory'],
    'environment_EnvironmentalProtection': ['geography', 'territory'],
    'environment_NatureProtection': ['geography', 'territory'],
    'society': ['geography', 'culture', 'population'],
    'health': ['geography', 'health'],
    'structure': ['geography', 'construction'],
    'transportation': ['geography', 'mobility'],
    'utilitiesCommunication': ['geography', 'territory', 'energy', 'culture'],
    'utilitiesCommunication_Energy': ['geography', 'energy', 'territory'],
    'utilitiesCommunication_Utilities': ['geography', 'territory'],
    'utilitiesCommunication_Communication': ['geography', 'culture'],
    'intelligenceMilitary': ['geography', 'public-order'],
    'farming': ['geography', 'agriculture'],
    'economy': ['geography', 'work', 'national-economy'],
}


def _get_category_mappings_as_set(swisstopo_groups):
    ogdch_categories = [
         mapping
         for group in swisstopo_groups
         if group in swisstopo_to_ogdch_group_mapping.keys()
         for mapping in swisstopo_to_ogdch_group_mapping[group]
    ]
    return set(ogdch_categories)


class DcatMetadata(object):
    """ Provides general access to dataset metadata for DCAT-AP Switzerland """

    def get_mapping(self):
        """
        Abstract method to define the dict
        of mapping fields
        """
        raise NotImplementedError

    def get_metadata(self):
        """
        Abstract method that returns the loaded metadata as a dict
        as an iterable (generator)
        """
        raise NotImplementedError

    def load(self, meta_xml, include_raw=False):
        if isinstance(meta_xml, basestring):
            meta_xml = loader.from_string(meta_xml)
        mapping = self.get_mapping()
        dcat_metadata = {}
        for key, attribute in mapping.items():
            dcat_metadata[key] = attribute.get_value(
                xml=meta_xml
            )
        if include_raw:
            return (self._clean_dataset(dcat_metadata), dcat_metadata)
        return self._clean_dataset(dcat_metadata)

    def _clean_dataset(self, dataset):
        cleaned_dataset = defaultdict(dict)

        # create language dicts from the suffixed keys
        cleaned_dataset = self._clean_suffixed_lang(dataset, cleaned_dataset)

        clean_values = {}
        for k in ('issued', 'modified'):
            try:
                clean_values[k] = self._clean_datetime(cleaned_dataset[k])
            except ValueError:
                continue

        if all(x in cleaned_dataset
                for x in ['temporals_start', 'temporals_end']):
            clean_values['temporals'] = self._clean_temporals(cleaned_dataset)
            del cleaned_dataset['temporals_start']
            del cleaned_dataset['temporals_end']

        clean_values['publishers'] = self._clean_publishers(cleaned_dataset)
        clean_values['contact_points'] = self._clean_contact_points(
            cleaned_dataset
        )
        clean_values['relations'] = self._clean_relations(cleaned_dataset)
        clean_values['keywords'] = self._clean_keywords(cleaned_dataset)
        clean_values['groups'] = self._clean_groups(cleaned_dataset)
        clean_values['accrual_periodicity'] = self._clean_accrual_periodicity(
            cleaned_dataset
        )

        # copy all cleaned values if they were in the dict before
        # this is needed as the same cleaning code is used for dataset
        # and distributions, but they don't have the same keys
        for key, value in clean_values.iteritems():
            if key in cleaned_dataset:
                cleaned_dataset[key] = value

        # set the issued date to today if it's not given
        if not cleaned_dataset['issued']:
            cleaned_dataset['issued'] = int(time.time())

        # clean see_alsos
        if 'see_alsos' in cleaned_dataset and not cleaned_dataset['see_alsos']:
            cleaned_dataset['see_alsos'] = []

        # remove rights here, only needed on distributions
        cleaned_dataset.pop('rights', None)

        clean_dict = dict(cleaned_dataset)
        log.debug("Cleaned dataset: %s" % clean_dict)

        return clean_dict

    def _clean_suffixed_lang(self, dataset, cleaned_dataset):
        for k in dataset:
            if k.endswith(('_de', '_fr', '_it', '_en')):
                cleaned_dataset[k[:-3]][k[-2:]] = dataset[k]
            else:
                cleaned_dataset[k] = dataset[k]
        return cleaned_dataset

    def _clean_datetime(self, datetime_value):
        try:
            d = datetime.strptime(
                datetime_value[0:len('YYYY-MM-DD')],
                '%Y-%m-%d'
            )
            # we have to calculate this manually since the
            # time library of Python 2.7 does not support
            # years < 1900, see OGD-751 and the time docs
            # https://docs.python.org/2.7/library/time.html
            epoch = datetime(1970, 1, 1)
            return int((d - epoch).total_seconds())
        except (ValueError, KeyError, TypeError, IndexError):
            raise ValueError("Could not parse datetime")

    def _clean_temporals(self, pkg_dict):
        values = {}
        try:
            for k in ('temporals_start', 'temporals_end'):
                values[k] = self._clean_datetime(pkg_dict[k])
            return [{
                'start_date': values['temporals_start'],
                'end_date': values['temporals_end'],
            }]
        except ValueError:
            return []

    def _clean_publishers(self, pkg_dict):
        publishers = []
        if 'publishers' in pkg_dict:
            for publisher in pkg_dict['publishers']:
                publishers.append({'label': publisher})
        return publishers

    def _clean_contact_points(self, pkg_dict):
        contacts = []
        if 'contact_points' in pkg_dict:
            for contact in pkg_dict['contact_points']:
                contacts.append({'email': contact, 'name': contact})
        return contacts

    def _clean_relations(self, pkg_dict):
        relations = []
        if 'relations' in pkg_dict:
            for relation in pkg_dict['relations']:
                try:
                    label = relation[1] if relation[1] else relation[0]
                    relation_dict = {'url': relation[0], 'label': label}
                except IndexError:
                    relation_dict = {'url': relation, 'label': relation}
                # check if the URL is valid
                try:
                    self._validate_url(relation_dict['url'])
                    relations.append(relation_dict)
                except ValueError:
                    log.debug("Invalid relation URL, skipping relation...")
                    continue

        return relations

    def _validate_url(self, url):
        result = urlparse(url)
        if not result.scheme or not result.netloc or result.netloc == '-':
            raise ValueError("The provided URL '%s' is invalid (missing scheme or netloc)" % url)  # noqa
        return True

    def _clean_keywords(self, pkg_dict):
        clean_keywords = {}
        if 'keywords' in pkg_dict:
            for lang, tag_list in pkg_dict['keywords'].iteritems():
                clean_keywords[lang] = [munge_tag(tag) for tag in tag_list if tag != 'opendata.swiss']  # noqa
        return clean_keywords

    def _clean_groups(self, pkg_dict):
        ogdch_groups = []
        if 'groups' in pkg_dict:
            mapped_categories_set = _get_category_mappings_as_set(
                pkg_dict['groups'])
            ogdch_groups = [{'name': mapping}
                            for mapping in mapped_categories_set]
        return ogdch_groups

    def _clean_accrual_periodicity(self, pkg_dict):
        if 'accrual_periodicity' not in pkg_dict:
            return ''
        frequency_mapping = {
            'continual': 'http://purl.org/cld/freq/continuous',
            'daily': 'http://purl.org/cld/freq/daily',
            'weekly': 'http://purl.org/cld/freq/weekly',
            'fortnightly': 'http://purl.org/cld/freq/biweekly',
            'monthly': 'http://purl.org/cld/freq/monthly',
            'quarterly': 'http://purl.org/cld/freq/quarterly',
            'biannually': 'http://purl.org/cld/freq/semiannual',
            'annually': 'http://purl.org/cld/freq/annual',
            'asNeeded': 'http://purl.org/cld/freq/completelyIrregular',
            'irregular': 'http://purl.org/cld/freq/completelyIrregular',
        }
        log.debug(
            "Trying to map periodicity '%s'" % pkg_dict['accrual_periodicity']
        )
        try:
            return frequency_mapping[pkg_dict['accrual_periodicity']]
        except (KeyError, TypeError):
            return ''


class GeocatDcatDatasetMetadata(DcatMetadata):
    """ Provides access to the Geocat metadata """
    def __init__(self):
        super(GeocatDcatDatasetMetadata, self).__init__()
        self.csw = CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')
        self.dist = GeocatDcatDistributionMetadata()

    def get_metadata(self, xml_elem):
        dataset = self.load(xml_elem)

        if 'temporals' not in dataset:
            dataset['temporals'] = []

        if 'id' not in dataset:
            dataset['id'] = ''

        lang_mapping = {
            'ger': 'de',
            'fra': 'fr',
            'eng': 'en',
            'ita': 'it',
        }
        try:
            language = [lang_mapping[dataset['language']]]
        except KeyError:
            language = []
        dataset['language'] = language

        return dataset

    def get_mapping(self):
        return {
            'identifier': XPathValue('//gmd:fileIdentifier/gco:CharacterString/text()'),  # noqa
            'title_de': XPathValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#DE"]/text()'),  # noqa
            'title_fr': XPathValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#FR"]/text()'),  # noqa
            'title_it': XPathValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#IT"]/text()'),  # noqa
            'title_en': XPathValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#EN"]/text()'),  # noqa
            'description_de': XPathValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#DE"]/text()'),  # noqa
            'description_fr': XPathValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#FR"]/text()'),  # noqa
            'description_it': XPathValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#IT"]/text()'),  # noqa
            'description_en': XPathValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#EN"]/text()'),  # noqa
            'issued': FirstInOrderValue(
                [
                    XPathValue('//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "publication"]//gco:DateTime/text() | //gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "publication"]//gco:Date/text()'),  # noqa
                    XPathValue('//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "creation"]//gco:DateTime/text() | //gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "creation"]//gco:Date/text()'),  # noqa
                    XPathValue('//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:DateTime/text() | //gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date/text()'),  # noqa
                ]
            ),
            'modified': XPathValue('//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:DateTime/text() | //gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date/text()'),  # noqa
            'publishers': ArrayValue([
                FirstInOrderValue(
                    [
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "publisher"]//gmd:organisationName/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "owner"]//gmd:organisationName/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "pointOfContact"]//gmd:organisationName/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "distributor"]//gmd:organisationName/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "custodian"]//gmd:organisationName/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:contact//che:CHE_CI_ResponsibleParty//gmd:organisationName/gco:CharacterString'),  # noqa
                    ]
                )
            ]),
            'contact_points': ArrayValue([
                FirstInOrderValue(
                    [
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "publisher"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "owner"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "pointOfContact"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "distributor"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "custodian"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString/text()'),  # noqa
                        XPathValue('//gmd:contact//che:CHE_CI_ResponsibleParty//gmd:address//gmd:electronicMailAddress/gco:CharacterString/text()'),  # noqa
                    ]
                )
            ]),
            'groups': XPathMultiValue('//gmd:identificationInfo//gmd:topicCategory/gmd:MD_TopicCategoryCode/text()'),  # noqa
            'language': FirstInOrderValue(
                [
                    XPathValue('//gmd:identificationInfo//gmd:language/gco:CharacterString/text()'),  # noqa
                    XPathValue('//che:CHE_MD_Metadata/gmd:language/gco:CharacterString/text()'),  # noqa
                ]
            ),
            'relations': ArrayValue(
                [
                    XPathSubValue(
                        '(//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"])[position()>1]',  # noqa
                        sub_attributes=[
                            FirstInOrderValue([
                                XPathValue('.//che:LocalisedURL[@locale = "#DE"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL[@locale = "#FR"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL[@locale = "#EN"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL[@locale = "#IT"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL/text()'),  # noqa
                            ]),
                            XPathValue('.//gmd:description/gco:CharacterString/text()'),  # noqa
                        ]
                    ),
                    XPathSubValue(
                        '(//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "CHTOPO:specialised-geoportal"])',  # noqa
                        sub_attributes=[
                            FirstInOrderValue([
                                XPathValue('.//che:LocalisedURL[@locale = "#DE"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL[@locale = "#FR"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL[@locale = "#EN"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL[@locale = "#IT"]/text()'),  # noqa
                                XPathValue('.//che:LocalisedURL/text()'),  # noqa
                            ]),
                            XPathValue('.//gmd:description/gco:CharacterString/text()'),  # noqa
                        ]
                    ),
                ]
            ),
            'keywords_de': XPathMultiValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#DE"]/text()'),  # noqa
            'keywords_fr': XPathMultiValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#FR"]/text()'),  # noqa
            'keywords_it': XPathMultiValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#IT"]/text()'),  # noqa
            'keywords_en': XPathMultiValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#EN"]/text()'),  # noqa
            'url': FirstInOrderValue([
                XPathValue('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL[@locale = "#DE"]/text()'),  # noqa
                XPathValue('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL[@locale = "#FR"]/text()'),  # noqa
                XPathValue('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL[@locale = "#EN"]/text()'),  # noqa
                XPathValue('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL[@locale = "#IT"]/text()'),  # noqa
                XPathValue('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL/text()'),  # noqa
            ]),
            'spatial': XPathValue('//gmd:identificationInfo//gmd:extent//gmd:description/gco:CharacterString/text()'),  # noqa
            'coverage': StringValue(''),  # noqa
            'temporals_start': XPathValue('//gmd:identificationInfo//gmd:extent//gmd:temporalElement//gml:TimePeriod/gml:beginPosition/text()'),  # noqa
            'temporals_end': XPathValue('//gmd:identificationInfo//gmd:extent//gmd:temporalElement//gml:TimePeriod/gml:endPosition/text()'),  # noqa
            'accrual_periodicity': XPathValue('//gmd:identificationInfo//che:CHE_MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode/@codeListValue'),  # noqa
            'see_alsos': XPathMultiValue('//gmd:identificationInfo//gmd:aggregationInfo//gmd:aggregateDataSetIdentifier/gmd:MD_Identifier/gmd:code/gco:CharacterString/text()'),  # noqa
            'rights': FirstInOrderValue(
                [
                    XPathValue('.//gmd:resourceConstraints//gmd:otherConstraints//gmd:LocalisedCharacterString[@locale = "#DE" and ./text()]/text()'),  # noqa
                    XPathValue('.//gmd:resourceConstraints//gmd:otherConstraints//gmd:LocalisedCharacterString[@locale = "#FR" and ./text()]/text()'),  # noqa
                ]
            ),
        }


class GeocatDcatDistributionMetadata(DcatMetadata):
    """ Provides access to the Geocat metadata """
    def __init__(self):
        super(GeocatDcatDistributionMetadata, self).__init__()
        self.csw = CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')

    def get_metadata(self, xml):
        dataset_meta = self._get_dataset_metadata(xml)
        distributions = []

        # handle downloads
        download_dist = GeocatDcatDownloadDistributionMetadata()
        download_dists = download_dist.get_metadata(xml, dataset_meta)
        distributions.extend(download_dists)

        # handle services
        service_dist = GeocatDcatServiceDistributionMetadata()
        service_dists = service_dist.get_metadata(xml, dataset_meta)
        distributions.extend(service_dists)

        # handle service datasets
        service_dataset = GeocatDcatServiceDatasetMetadata()
        service_datasets = service_dataset.get_metadata(xml, dataset_meta)
        distributions.extend(service_datasets)

        return distributions

    # Use the original dist as template to create a new dist.
    # and delete the url_list on the copy as we don't need it afterwards.
    def _create_dist_copy(self, orig_dist, access_url):
        dist = orig_dist.copy()
        dist['url'] = access_url

        del dist['url_list']
        return dist

    def _get_dataset_metadata(self, xml):
        dataset = GeocatDcatDatasetMetadata()

        # TODO: include_raw is an ugly hack to be able to get all extracted
        # attributes. In this case we need to access the 'rights' attribute,
        # which we extract on the dataset level. It is not available otherwise
        # on the distribution level. Since we "clean" the dataset after the
        # extraction (i.e. only the allowed attributes stay in the dict) we
        # need to access the "raw" dataset metadata to get the value anyway.
        # We should refactor this, to i.e. make the complete data always
        # available to the distributions
        dataset_meta, raw_meta = dataset.load(xml, include_raw=True)

        # copy rights from raw metadata
        dataset_meta['rights'] = raw_meta.get('rights')

        # add media_type to dataset metadata
        dataset_meta['media_type'] = ''
        service_media_type = loader.xpath(xml, '//gmd:identificationInfo//srv:serviceType/gco:LocalName/text()')  # noqa
        dist_media_type = loader.xpath(xml, '//gmd:distributionInfo//gmd:distributionFormat//gmd:name//gco:CharacterString/text()')  # noqa

        if service_media_type:
            try:
                dataset_meta['media_type'] = service_media_type[0]
            except IndexError:
                pass

        if dist_media_type:
            try:
                dataset_meta['media_type'] = dist_media_type[0]
            except IndexError:
                pass

        # if the media type is set to 'N/A', consider this an empty value
        if dataset_meta['media_type'].upper() == 'N/A':
            dataset_meta['media_type'] = ''

        return dataset_meta

    def _handle_single_distribution(self, dist_xml, dataset_meta):
        dist = self.load(dist_xml)

        dist['language'] = []
        for loc, loc_url in dist['loc_url'].iteritems():
            if loc_url:
                dist['language'].append(loc)
        del dist['loc_url']

        protocol_title = {
            "OGC:WMTS-http-get-capabilities": "WMTS (GetCapabilities)",
            "OGC:WMS-http-get-map": "WMS (GetMap)",
            "OGC:WMS-http-get-capabilities": "WMS (GetCapabilities)",
            "OGC:WFS-http-get-capabilities": "WFS (GetCapabilities)",
            "WWW:DOWNLOAD-1.0-http--download": "Download",
            "WWW:DOWNLOAD-URL": "Download",
        }
        try:
            title = protocol_title[dist['protocol']]
        except KeyError:
            title = ''
        if dist['name']:
            title += ' %s' % dist['name']
        title = title.strip()
        if title:
            dist['title'] = {
                "de": title,
                "fr": title,
                "it": title,
                "en": title,
            }
        else:
            dist['title'] = dict(dist['description'])

        # map rights
        rights = {
            u'Freie Nutzung': 'NonCommercialAllowed-CommercialAllowed-ReferenceNotRequired',  # noqa
            u'Utilisation libre': 'NonCommercialAllowed-CommercialAllowed-ReferenceNotRequired',  # noqa

            u'Freie Nutzung. Quellenangabe ist Pflicht.': 'NonCommercialAllowed-CommercialAllowed-ReferenceRequired',  # noqa
            u'Utilisation libre. Obligation d’indiquer la source.': 'NonCommercialAllowed-CommercialAllowed-ReferenceRequired',  # noqa

            u'Freie Nutzung. Kommerzielle Nutzung nur mit Bewilligung des Datenlieferanten zulässig.': 'NonCommercialAllowed-CommercialWithPermission-ReferenceNotRequired',  # noqa
            u'Utilisation libre. Utilisation à des fins commerciales uniquement avec l’autorisation du fournisseur des données.': 'NonCommercialAllowed-CommercialWithPermission-ReferenceNotRequired',  # noqa

            u'Freie Nutzung. Quellenangabe ist Pflicht. Kommerzielle Nutzung nur mit Bewilligung des Datenlieferanten zulässig.': 'NonCommercialAllowed-CommercialWithPermission-ReferenceRequired',  # noqa
            u'Utilisation libre. Obligation d’indiquer la source. Utilisation commerciale uniquement avec l’autorisation du fournisseur des données.': 'NonCommercialAllowed-CommercialWithPermission-ReferenceRequired' # noqa
        }
        if dataset_meta.get('rights') in rights:
            dist['rights'] = rights[dataset_meta['rights']]
        else:
            dist['rights'] = ''
        del dist['name']
        del dist['protocol']

        dist['issued'] = dataset_meta['issued']
        dist['modified'] = dataset_meta['modified']
        dist['format'] = ''
        dist['media_type'] = dataset_meta.get('media_type', '')

        return dist


class GeocatDcatDownloadDistributionMetadata(GeocatDcatDistributionMetadata):
    """ Provides access to the Geocat metadata """

    def get_metadata(self, xml, dataset_meta):
        download_distributions = []
        for dist_xml in loader.xpath(xml, '//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:DOWNLOAD-1.0-http--download" or .//gmd:protocol/gco:CharacterString/text() = "WWW:DOWNLOAD-URL"]'):  # noqa
            orig_dist = self._handle_single_distribution(
                dist_xml,
                dataset_meta
            )
            try:
                for url in orig_dist['url_list']:
                    dist = self._create_dist_copy(orig_dist, url)
                    self._validate_url(dist.get('download_url'))
                    self._validate_url(dist.get('url'))
                    download_distributions.append(dist)
            except (ValueError, KeyError):
                log.debug("URL in resource invalid ('%s' or '%s'), skipping resource..." % (dist.get('download_url'), dist.get('url')))  # noqa
                continue
        return download_distributions

    def get_mapping(self):
        return {
            'name': XPathValue('.//gmd:name/gco:CharacterString/text()'),
            'protocol': XPathValue('.//gmd:protocol/gco:CharacterString/text()'),  # noqa
            'language': StringValue(''),  # noqa
            # 'download_url' and 'url' are set to empty, their
            # values will be determined and set later from 'url_list'
            'download_url': StringValue(''),  # noqa
            'url': StringValue(''),  # noqa
            'url_list': FirstInOrderValue(
                [
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#DE" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#FR" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#EN" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#IT" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//gmd:URL[./text()]/text()'),   # noqa
                ]
            ),
            'description_de': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#DE"]/text()'),  # noqa
            'description_fr': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#FR"]/text()'),  # noqa
            'description_it': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#IT"]/text()'),  # noqa
            'description_en': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#EN"]/text()'),  # noqa
            'loc_url_de': XPathValue('.//che:LocalisedURL[@locale = "#DE"]/text()'),  # noqa
            'loc_url_fr': XPathValue('.//che:LocalisedURL[@locale = "#FR"]/text()'),  # noqa
            'loc_url_it': XPathValue('.//che:LocalisedURL[@locale = "#IT"]/text()'),  # noqa
            'loc_url_en': XPathValue('.//che:LocalisedURL[@locale = "#EN"]/text()'),  # noqa
            'license': StringValue(''),  # noqa
            'identifier': StringValue(''),  # noqa
            'rights': StringValue(''),
            'byte_size': StringValue(''),
            'media_type': StringValue(''),
            'format': StringValue(''),
            'coverage': StringValue(''),
        }

    # Use the original dist as template to create a new dist.
    # Also set the url to the access_url (and the download_url if it exists)
    # and delete the url_list on the copy as we don't need it afterwards.
    def _create_dist_copy(self, orig_dist, access_url):
        dist = super(GeocatDcatDownloadDistributionMetadata, self)._create_dist_copy(orig_dist, access_url)  # noqa

        dist['download_url'] = access_url

        # if a download URL ends with zip,
        # assume the media type is application/zip, no matter what geocat says
        try:
            if dist['download_url'].endswith('.zip'):
                dist['media_type'] = 'application/zip'
        except (KeyError, AttributeError):
            pass

        return dist


class GeocatDcatServiceDistributionMetadata(GeocatDcatDistributionMetadata):
    """ Provides access to the Geocat metadata """

    def get_metadata(self, xml, dataset_meta):
        service_distributions = []
        for dist_xml in loader.xpath(xml, '//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "OGC:WMTS-http-get-capabilities" or .//gmd:protocol/gco:CharacterString/text() = "OGC:WMS-http-get-map" or .//gmd:protocol/gco:CharacterString/text() = "OGC:WMS-http-get-capabilities" or .//gmd:protocol/gco:CharacterString/text() = "OGC:WFS-http-get-capabilities"]'):  # noqa
            orig_dist = self._handle_single_distribution(
                dist_xml,
                dataset_meta
            )
            orig_dist['media_type'] = ''
            try:
                for url in orig_dist['url_list']:
                    dist = self._create_dist_copy(orig_dist, url)
                    self._validate_url(dist.get('url'))
                    service_distributions.append(dist)
            except (ValueError, KeyError):
                log.debug("URL in resource invalid ('%s'), skipping resource..." % dist.get('url'))  # noqa
                continue
        return service_distributions

    def get_mapping(self):
        return {
            'name': XPathValue('.//gmd:name/gco:CharacterString/text()'),  # noqa
            'protocol': XPathValue('.//gmd:protocol/gco:CharacterString/text()'),  # noqa
            'language': ArrayValue([]),  # noqa
            'url_list': FirstInOrderValue(
                [
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#DE" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#FR" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#EN" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[@locale = "#IT" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//gmd:linkage//che:LocalisedURL[./text()]/text()'),  # noqa
                ]
            ),
            'download_url': StringValue(''),  # noqa
            'description_de': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#DE"]/text()'),  # noqa
            'description_fr': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#FR"]/text()'),  # noqa
            'description_it': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#IT"]/text()'),  # noqa
            'description_en': XPathValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#EN"]/text()'),  # noqa
            'loc_url_de': XPathValue('.//che:LocalisedURL[@locale = "#DE"]/text()'),  # noqa
            'loc_url_fr': XPathValue('.//che:LocalisedURL[@locale = "#FR"]/text()'),  # noqa
            'loc_url_it': XPathValue('.//che:LocalisedURL[@locale = "#IT"]/text()'),  # noqa
            'loc_url_en': XPathValue('.//che:LocalisedURL[@locale = "#EN"]/text()'),  # noqa
            'license': StringValue(''),  # noqa
            'identifier': StringValue(''),  # noqa
            'rights': StringValue(''),  # noqa
            'byte_size': StringValue(''),  # noqa
            'media_type': StringValue(''),  # noqa
            'format': StringValue(''),  # noqa
            'coverage': StringValue(''),  # noqa
        }


class GeocatDcatServiceDatasetMetadata(GeocatDcatDistributionMetadata):
    """ Provides access to the Geocat metadata """

    def get_metadata(self, xml, dataset_meta):
        service_datasets = []
        for dist_xml in loader.xpath(xml, '//gmd:identificationInfo//srv:containsOperations/srv:SV_OperationMetadata[.//srv:operationName//gco:CharacterString/text()]'):  # noqa
            orig_dist = super(GeocatDcatServiceDatasetMetadata, self).load(dist_xml)  # noqa
            orig_dist['description'] = dataset_meta['description']
            orig_dist['issued'] = dataset_meta['issued']
            orig_dist['modified'] = dataset_meta['modified']
            orig_dist['format'] = ''
            orig_dist['media_type'] = dataset_meta.get('media_type', '')
            orig_dist['rights'] = dataset_meta.get('rights', '')
            try:
                for url in orig_dist['url_list']:
                    dist = self._create_dist_copy(orig_dist, url)
                    self._validate_url(dist.get('url'))
                    service_datasets.append(dist)
            except ValueError:
                log.debug("URL in resource invalid ('%s'), skipping resource..." % dist.get('url'))  # noqa
                continue
        return service_datasets

    def get_mapping(self):
        return {
            'title_de': XPathValue('.//srv:operationName/gco:CharacterString/text()'),  # noqa
            'title_fr': XPathValue('.//srv:operationName/gco:CharacterString/text()'),  # noqa
            'title_it': XPathValue('.//srv:operationName/gco:CharacterString/text()'),  # noqa
            'title_en': XPathValue('.//srv:operationName/gco:CharacterString/text()'),  # noqa
            'language': ArrayValue([]),  # noqa
            'url': StringValue(''),  # noqa
            'url_list': FirstInOrderValue(
                [
                    XPathMultiValue('.//srv:connectPoint//gmd:linkage//che:LocalisedURL[@locale = "#DE" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//srv:connectPoint//gmd:linkage//che:LocalisedURL[@locale = "#FR" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//srv:connectPoint//gmd:linkage//che:LocalisedURL[@locale = "#EN" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//srv:connectPoint//gmd:linkage//che:LocalisedURL[@locale = "#IT" and ./text()]/text()'),  # noqa
                    XPathMultiValue('.//srv:connectPoint//gmd:linkage//che:LocalisedURL[./text()]/text()'),  # noqa
                ]
            ),
            'description': StringValue(''),
            'license': StringValue(''),  # noqa
            'identifier': StringValue(''),  # noqa
            'download_url': StringValue(''),  # noqa
            'byte_size': StringValue(''),  # noqa
            'media_type': StringValue(''),  # noqa
            'format': StringValue(''),  # noqa
            'coverage': StringValue(''),  # noqa
            'rights': FirstInOrderValue(
                [
                    XPathValue('.//gmd:resourceConstraints//gmd:otherConstraints//gmd:LocalisedCharacterString[@locale = "#DE" and ./text()]/text()'),  # noqa
                    XPathValue('.//gmd:resourceConstraints//gmd:otherConstraints//gmd:LocalisedCharacterString[@locale = "#FR" and ./text()]/text()'),  # noqa
                ]
            ),
        }


class GeocatCatalogueServiceWeb(CatalogueServiceWeb):
    def __init__(self, *args, **kwargs):
        self.xml_elem = defaultdict()
        super(GeocatCatalogueServiceWeb, self).__init__(*args, **kwargs)

    def _parserecords(self, outputschema, esn):
        if outputschema == loader.namespaces['che']:
            for i in self._exml.findall('//'+util.nspath('CHE_MD_Metadata', loader.namespaces['che'])):  # noqa
                val = i.find(util.nspath('fileIdentifier', loader.namespaces['gmd']) + '/' + util.nspath('CharacterString', loader.namespaces['gco']))  # noqa
                identifier = self._setidentifierkey(util.testXMLValue(val))
                self.records[identifier] = iso.MD_Metadata(i)
                self.xml_elem[identifier] = i
        else:
            super(
                GeocatCatalogueServiceWeb, self
            )._parserecords(outputschema, esn)


class CswHelper(object):
    def __init__(self, url='http://www.geocat.ch/geonetwork/srv/eng/csw'):
        self.catalog = GeocatCatalogueServiceWeb(url, skip_caps=True)
        self.schema = loader.namespaces['che']

    def get_id_by_search(self, searchterm='', propertyname='csw:AnyText',
                         cql=None):
        """ Returns the found csw dataset with the given searchterm """
        if cql is None:
            cql = "%s like '%%%s%%'" % (propertyname, searchterm)

        nextrecord = 0
        while nextrecord is not None:
            self._make_csw_request(cql, startposition=nextrecord)

            log.debug("----------------------------------------")
            log.debug("CSW Result: %s" % self.catalog.results)
            log.debug("----------------------------------------")

            if (self.catalog.response is None or
                    self.catalog.results['matches'] == 0):
                raise DatasetNotFoundError(
                    "No dataset for the given cql '%s' found" % cql
                )

            # return a generator
            for id in self.catalog.records:
                yield id

            if (self.catalog.results['returned'] > 0 and
                    self.catalog.results['nextrecord'] > 0):
                nextrecord = self.catalog.results['nextrecord']
            else:
                nextrecord = None

    def _make_csw_request(self, cql, startposition=0):
        self.catalog.getrecords(
            cql=cql,
            outputschema=self.schema,
            maxrecords=50,
            startposition=startposition
        )

    def get_by_id(self, id):
        """ Returns the csw dataset with the given id """
        self.catalog.getrecordbyid(id=[id], outputschema=self.schema)
        return self.catalog.response


class DatasetNotFoundError(Exception):
    pass


class MappingNotFoundError(Exception):
    pass
