from lxml import etree
from datetime import datetime
import time
from collections import defaultdict
from owslib.csw import CatalogueServiceWeb
from owslib import util
import owslib.iso as iso
import logging
from ckan.lib.munge import munge_title_to_name, munge_tag
log = logging.getLogger(__name__)

namespaces = {
    'atom': 'http://www.w3.org/2005/Atom',
    'che': 'http://www.geocat.ch/2008/che',
    'csw': 'http://www.opengis.net/cat/csw/2.0.2',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dct': 'http://purl.org/dc/terms/',
    'ddi': 'http://www.icpsr.umich.edu/DDI',
    'dif': 'http://gcmd.gsfc.nasa.gov/Aboutus/xml/dif/',
    'fgdc': 'http://www.opengis.net/cat/csw/csdgm',
    'gco': 'http://www.isotc211.org/2005/gco',
    'gmd': 'http://www.isotc211.org/2005/gmd',
    'gml': 'http://www.opengis.net/gml',
    'ogc': 'http://www.opengis.net/ogc',
    'ows': 'http://www.opengis.net/ows',
    'rim': 'urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'srv': 'http://www.isotc211.org/2005/srv',
    'xs': 'http://www.w3.org/2001/XMLSchema',
    'xs2': 'http://www.w3.org/XML/Schema',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}


class Value(object):
    def __init__(self, config, **kwargs):
        self._config = config
        self.env = kwargs

    def get_value(self, **kwargs):
        """ Abstract method to return the value of the attribute """
        raise NotImplementedError


class StringValue(Value):
    def get_value(self, **kwargs):
        return self._config


class XmlValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        xml = self.env['xml']
        return etree.tostring(xml)


class XPathValue(Value):
    def get_element(self, xml, xpath):
        result = xml.xpath(xpath, namespaces=namespaces)
        if len(result) > 0:
            return result[0]
        return []

    def get_value(self, **kwargs):
        self.env.update(kwargs)
        xml = self.env['xml']

        xpath = self._config
        log.debug("XPath: %s" % (xpath))

        try:
            # this should probably return a XPathTextValue
            value = self.get_element(xml, xpath)
        except etree.XPathError, e:
            log.debug('XPath not found: %s, error: %s' % (xpath, str(e)))
            value = ''
        return value


class XPathMultiValue(XPathValue):
    def get_element(self, xml, xpath):
        return xml.xpath(xpath, namespaces=namespaces)


class XPathTextValue(XPathValue):
    def get_value(self, **kwargs):
        value = super(XPathTextValue, self).get_value(**kwargs)
        if (hasattr(value, 'text') and
                value.text is not None and
                value.text.strip() != ''):
            return value.text.strip()
        elif isinstance(value, basestring):
            return value
        else:
            return ''


class XPathMultiTextValue(XPathMultiValue):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        values = super(XPathMultiTextValue, self).get_value(**kwargs)
        return_values = []
        for value in values:
            if (hasattr(value, 'text') and
                    value.text is not None and
                    value.text.strip() != ''):
                return_values.append(value.text.strip())
            elif isinstance(value, basestring):
                return_values.append(value)
        return return_values


class CombinedValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        value = ''
        separator = self.env['separator'] if 'separator' in self.env else ' '
        for attribute in self._config:
            new_value = attribute.get_value(**kwargs)
            if new_value is not None:
                value = value + attribute.get_value(**kwargs) + separator
        return value.strip(separator)


class DateCollectionValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        separator = self.env['separator'] if 'separator' in self.env else ' '

        start_dates = self._config[0].get_value(**kwargs)
        end_dates = self._config[1].get_value(**kwargs)
        cycles = self._config[2].get_value(**kwargs)

        value = ''
        for i, date in enumerate(start_dates):
            value += date + ' - '
            if i <= len(end_dates) - 1:
                value += end_dates[i]
            if i <= len(cycles) - 1:
                value += ': ' + cycles[i]
            value += separator

        return value.strip(separator)


class MultiValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        value = ''
        separator = self.env['separator'] if 'separator' in self.env else ' '
        for attribute in self._config:
            new_value = attribute.get_value(**kwargs)
            try:
                iterator = iter(new_value)
                for inner_attribute in iterator:
                    # it should be possible to call inner_attribute.get_value
                    # and the right thing(tm) happens'
                    if hasattr(inner_attribute, 'text'):
                        value = value + inner_attribute.text
                    else:
                        value = value + inner_attribute
                    value = value + separator
            except TypeError:
                value = value + new_value + separator
        return value.strip(separator)


class ArrayValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        value = []
        for attribute in self._config:
            new_value = attribute.get_value(**kwargs)
            try:
                iterator = iter(new_value)
                for inner_attribute in iterator:
                    # it should be possible to call inner_attribute.get_value
                    # and the right thing(tm) happens'
                    if hasattr(inner_attribute, 'text'):
                        value.append(inner_attribute.text)
                    else:
                        value.append(inner_attribute)
            except TypeError:
                value.append(new_value)
        return value


class ArrayTextValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        values = self._config.get_value(**kwargs)
        separator = self.env['separator'] if 'separator' in self.env else ' '
        return separator.join(values)


class ArrayDictNameValue(ArrayValue):
    def get_value(self, **kwargs):
        value = super(ArrayDictNameValue, self).get_value(**kwargs)
        return self.wrap_in_name_dict(value)

    def wrap_in_name_dict(self, values):
        return [{'name': munge_title_to_name(value)} for value in values]


class FirstInOrderValue(CombinedValue):
    def get_value(self, **kwargs):
        for attribute in self._config:
            value = attribute.get_value(**kwargs)
            if value != '':
                return value
        return ''


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

    def get_metadata_keys(self):
        return self.get_mapping().keys()

    def get_attribute(self, ckan_attribute):
        mapping = self.get_mapping()
        if ckan_attribute in mapping:
            return mapping[ckan_attribute]
        raise MappingNotFoundError(
            "No mapping found for attribute '%s'" % ckan_attribute
        )

    def load(self, meta_xml):
        if isinstance(meta_xml, basestring):
            try:
                meta_xml = etree.fromstring(meta_xml)
            except etree.XMLSyntaxError, e:
                raise MetadataFormatError('Could not parse XML: %r' % e)

        dcat_metadata = {}
        for key in self.get_metadata_keys():
            attribute = self.get_attribute(key)
            dcat_metadata[key] = attribute.get_value(
                xml=meta_xml
            )
        return self._clean_dataset(dcat_metadata)

    def _clean_dataset(self, dataset):
        cleaned_dataset = defaultdict(dict)
        for k in dataset:
            if k.endswith(('_de', '_fr', '_it', '_en')):
                cleaned_dataset[k[:-3]][k[-2:]] = dataset[k]
            else:
                cleaned_dataset[k] = dataset[k]

        for k in ('issued', 'modified'):
            try:
                d = datetime.strptime(cleaned_dataset[k], '%Y-%m-%d')
                cleaned_dataset[k] = int(time.mktime(d.timetuple()))
            except (ValueError, KeyError, TypeError):
                continue
        if not cleaned_dataset['issued']:
            cleaned_dataset['issued'] = datetime.strptime('1970-1-1', '%Y-%m-%d')

        if 'publishers' in cleaned_dataset:
            publishers = []
            for publisher in cleaned_dataset['publishers']:
                publishers.append({'label': publisher})
            cleaned_dataset['publishers'] = publishers

        if 'contact_points' in cleaned_dataset:
            contacts = []
            for contact in cleaned_dataset['contact_points']:
                contacts.append({'email': contact, 'name': contact})
            cleaned_dataset['contact_points'] = contacts

        if 'keywords' in cleaned_dataset:
            clean_keywords = {}
            for lang, tag_list in cleaned_dataset['keywords'].iteritems():
                clean_keywords[lang] = [munge_tag(tag) for tag in tag_list]
            cleaned_dataset['keywords'] = clean_keywords
                
        group_mapping = {
            'biota': 'agriculture',
            'health': 'health',
            'transportation': 'mobility',
            'intelligenceMilitary': 'public-order',
            'farming': 'agriculture',
            'economy': 'national-economy',
        }

        if 'groups' in cleaned_dataset:
            groups = [{'name': 'geography'}]
            for group in cleaned_dataset['groups']:
                if group in group_mapping:
                    groups.append({'name': group_mapping[group]})
                else:
                    groups.append({'name': 'territory'})
            cleaned_dataset['groups'] = groups

        clean_dict = dict(cleaned_dataset)
        log.debug("Cleaned dataset: %s" % clean_dict)

        return clean_dict


class GeocatDcatDatasetMetadata(DcatMetadata):
    """ Provides access to the Geocat metadata """
    def __init__(self):
        super(GeocatDcatDatasetMetadata, self).__init__()
        self.csw = CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')
        self.dist = GeocatDcatDistributionMetadata()

    def get_metadata(self, xml_elem):
        dataset = self.load(xml_elem)

        lang_mapping = {
            'ger': 'de',
            'fra': 'fr',
            'eng': 'en',
            'ita': 'it',
        }
        try:
            language = lang_mapping[dataset['language']]
        except KeyError:
            language = []
        dataset['language'] = language

        return dataset

    def get_mapping(self):
        return {
            'identifier': XPathTextValue('//gmd:fileIdentifier/gco:CharacterString'),  # noqa
            'title_de': XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#DE"]'),
            'title_fr': XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#FR"]'),
            'title_it': XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#IT"]'),
            'title_en': XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:title//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#EN"]'),
            'description_de': XPathTextValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#DE"]'),
            'description_fr': XPathTextValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#FR"]'),
            'description_it': XPathTextValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#IT"]'),
            'description_en': XPathTextValue('//gmd:identificationInfo//gmd:abstract//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#EN"]'),
            'issued': FirstInOrderValue(
                [
                    XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:date[.//gmd:CI_DateTypeCode/@codeListValue = "publication"]//gco:Date'),
                    XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:date[.//gmd:CI_DateTypeCode/@codeListValue = "creation"]//gco:Date'),
                    XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date'),
                ]
            ),
            'modified': XPathTextValue('//gmd:identificationInfo//gmd:citation//gmd:date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date'),
            'publishers': XPathMultiTextValue('//gmd:identificationInfo//gmd:pointOfContact//gmd:organisationName/gco:CharacterString'),
            'contact_points': ArrayValue(
                [
                    XPathMultiTextValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "pointOfContact"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString'),
                    XPathMultiTextValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "owner"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString'),
                    XPathMultiTextValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "custodian"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString'),
                    XPathMultiTextValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "distributor"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString'),
                    XPathMultiTextValue('//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "publisher"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString'),
                ]
            ),
            'groups': XPathMultiTextValue('//gmd:identificationInfo//gmd:topicCategory/gmd:MD_TopicCategoryCode'),
            'language': XPathTextValue('//gmd:identificationInfo//gmd:language/gco:CharacterString'),
            'relations': XPathTextValue('(.//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL)[position()>1]'),
            'keywords_de': XPathMultiTextValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#DE"]'),
            'keywords_fr': XPathMultiTextValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#FR"]'),
            'keywords_it': XPathMultiTextValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#IT"]'),
            'keywords_en': XPathMultiTextValue('//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword//gmd:textGroup//gmd:LocalisedCharacterString[@locale="#EN"]'),
            'url': XPathTextValue('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL'),
            'spatial': StringValue(''),
            'coverage': StringValue(''),
            'temporals': StringValue(''),
            'accrual_periodicity': StringValue(''),
            'see_alsos': StringValue(''),
        }


class GeocatDcatDistributionMetadata(DcatMetadata):
    """ Provides access to the Geocat metadata """
    def __init__(self):
        super(GeocatDcatDistributionMetadata, self).__init__()
        self.csw = CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')

    def get_metadata(self, xml_elem):
        dataset = GeocatDcatDatasetMetadata()
        dataset_meta = dataset.load(xml_elem)
        xml = etree.fromstring(xml_elem)

        # add media_type to dataset metadata
        try:
            dataset_meta['media_type'] = xml.xpath('//gmd:distributionInfo//gmd:distributionFormat//gmd:name//gco:CharacterString/text()', namespaces=namespaces)[0]
        except IndexError:
            pass

        distributions = []

        # handle downloads
        download_dist = GeocatDcatDownloadDistributionMetdata()
        for dist_xml in xml.xpath('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "WWW:DOWNLOAD-1.0-http--download" or .//gmd:protocol/gco:CharacterString/text() = "WWW:DOWNLOAD-URL"]', namespaces=namespaces):
            dist = download_dist.get_metadata(dist_xml, dataset_meta)
            distributions.append(dist)

        # handle services
        service_dist = GeocatDcatServiceDistributionMetdata()
        for dist_xml in xml.xpath('//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource[.//gmd:protocol/gco:CharacterString/text() = "CHTOPO:specialised-geoportal" or .//gmd:protocol/gco:CharacterString/text() = "OGC:WMTS-http-get-capabilities" or .//gmd:protocol/gco:CharacterString/text() = "OGC:WMS-http-get-map" or .//gmd:protocol/gco:CharacterString/text() = "OGC:WMS-http-get-capabilities" or .//gmd:protocol/gco:CharacterString/text() = "OGC:WFS-http-get-capabilities"]', namespaces=namespaces):
            dist = service_dist.get_metadata(dist_xml, dataset_meta)
            distributions.append(dist)
        
        return distributions

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
        del dist['name']
        del dist['protocol']

        dist['issued'] = dataset_meta['issued']
        dist['modified'] = dataset_meta['modified']
        dist['format'] = ''
        dist['media_type'] = dataset_meta['media_type']
        return dist


class GeocatDcatDownloadDistributionMetdata(GeocatDcatDistributionMetadata):
    """ Provides access to the Geocat metadata """

    def get_metadata(self, dist_xml, dataset_meta):
        dist = self._handle_single_distribution(dist_xml, dataset_meta)
        return dist

    def get_mapping(self):
        return {
            'name': XPathTextValue('.//gmd:name/gco:CharacterString'),
            'protocol': XPathTextValue('.//gmd:protocol/gco:CharacterString'),
            'language': StringValue(''),
            'url': XPathTextValue('.//gmd:linkage//che:LocalisedURL'),
            'description_de': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#DE"]'),
            'description_fr': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#FR"]'),
            'description_it': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#IT"]'),
            'description_en': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#EN"]'),
            'loc_url_de': XPathTextValue('.//che:LocalisedURL[@locale = "#DE"]'),
            'loc_url_fr': XPathTextValue('.//che:LocalisedURL[@locale = "#FR"]'),
            'loc_url_it': XPathTextValue('.//che:LocalisedURL[@locale = "#IT"]'),
            'loc_url_en': XPathTextValue('.//che:LocalisedURL[@locale = "#EN"]'),
            'license': StringValue(''),
            'identifier': StringValue(''),
            'download_url': XPathTextValue('.//gmd:linkage//che:LocalisedURL'),
            'byte_size': StringValue(''),
            'media_type': StringValue(''),
            'format': StringValue(''),
            'coverage': StringValue(''),
        }


class GeocatDcatServiceDistributionMetdata(GeocatDcatDistributionMetadata):
    """ Provides access to the Geocat metadata """

    def get_metadata(self, dist_xml, dataset_meta):
        dist = self._handle_single_distribution(dist_xml, dataset_meta)
        dist['media_type'] = ''
        return dist

    def get_mapping(self):
        return {
            'name': XPathTextValue('.//gmd:name/gco:CharacterString'),
            'protocol': XPathTextValue('.//gmd:protocol/gco:CharacterString'),
            'language': StringValue(''),
            'url': XPathTextValue('.//gmd:linkage//che:LocalisedURL'),
            'description_de': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#DE"]'),
            'description_fr': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#FR"]'),
            'description_it': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#IT"]'),
            'description_en': XPathTextValue('.//gmd:description//gmd:LocalisedCharacterString[@locale = "#EN"]'),
            'loc_url_de': XPathTextValue('.//che:LocalisedURL[@locale = "#DE"]'),
            'loc_url_fr': XPathTextValue('.//che:LocalisedURL[@locale = "#FR"]'),
            'loc_url_it': XPathTextValue('.//che:LocalisedURL[@locale = "#IT"]'),
            'loc_url_en': XPathTextValue('.//che:LocalisedURL[@locale = "#EN"]'),
            'license': StringValue(''),
            'identifier': StringValue(''),
            'download_url': StringValue(''),
            'byte_size': StringValue(''),
            'media_type': StringValue(''),
            'format': StringValue(''),
            'coverage': StringValue(''),
        }


class GeocatCatalogueServiceWeb(CatalogueServiceWeb):
    def __init__(self, *args, **kwargs):
        self.xml_elem = defaultdict()
        super(GeocatCatalogueServiceWeb, self).__init__(*args, **kwargs)

    def _parserecords(self, outputschema, esn):
        if outputschema == namespaces['che']:
            for i in self._exml.findall('//'+util.nspath('CHE_MD_Metadata', namespaces['che'])):
                val = i.find(util.nspath('fileIdentifier', namespaces['gmd']) + '/' + util.nspath('CharacterString', namespaces['gco']))
                identifier = self._setidentifierkey(util.testXMLValue(val))
                self.records[identifier] = iso.MD_Metadata(i)
                self.xml_elem[identifier] = i
        else:
            super(GeocatCatalogueServiceWeb, self)._parserecords(outputschema, esn)


class CswHelper(object):
    def __init__(self, url='http://www.geocat.ch/geonetwork/srv/eng/csw'):
        self.catalog = GeocatCatalogueServiceWeb(url, skip_caps=True)
        self.schema = namespaces['che']

    def get_id_by_search(self, searchterm='', propertyname='csw:AnyText', cql=None):
        """ Returns the found csw dataset with the given searchterm """
        if cql is None:
            cql = "%s like '%%%s%%'" % (propertyname, searchterm)

        nextrecord = 0
        while nextrecord is not None:
            self._make_csw_request(cql, startposition=nextrecord)


            log.debug("----------------------------------------")
            log.debug("CSW Result: %s" % self.catalog.results)
            log.debug("----------------------------------------")

            if self.catalog.response == None or self.catalog.results['matches'] == 0:
                raise DatasetNotFoundError("No dataset for the given searchterm '%s' (%s) found" % (searchterm, propertyname))

            # return a generator
            for id in self.catalog.records:
                yield id

            if self.catalog.results['returned'] > 0 and self.catalog.results['nextrecord'] > 0:
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


class MetadataFormatError(Exception):
    pass
