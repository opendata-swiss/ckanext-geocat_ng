# -*- coding: utf-8 -*-

from lxml import etree
import owslib
import rdflib
import re
import os
from datetime import datetime
from pprint import pprint
from collections import defaultdict
from ckan.lib.munge import munge_tag

LOCALES = ['DE', 'FR', 'EN', 'IT']

gmd_namespaces = {
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
    'gmx': 'http://www.isotc211.org/2005/gmx',
    'gml': 'http://www.opengis.net/gml',
    'ogc': 'http://www.opengis.net/ogc',
    'ows': 'http://www.opengis.net/ows',
    'rim': 'urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'srv': 'http://www.isotc211.org/2005/srv',
    'xs': 'http://www.w3.org/2001/XMLSchema',
    'xs2': 'http://www.w3.org/XML/Schema',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'xlink': 'http://www.w3.org/1999/xlink',
}

dcat_namespaces = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
    'foaf': 'http://xmlns.com/foaf/0.1/',
    'skos': 'http://www.w3.org/2004/02/skos/core#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#'
}

XPATH_NODE = 'node'
XPATH_TEXT = 'text'
XPATH_LOCALIZED_TEXT = 'localized_text'
XPATH_LOCALIZED_URL = 'localized_url'

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

def get_elem_tree_from_string(xml_string):
    try:
        xml_elem_tree = etree.fromstring(xml_string)
    except etree.XMLSyntaxError as e:
        raise MetadataFormatError('Could not parse XML: %r' % e)
    return xml_elem_tree

class GeodataRecordMapping(object):

    def __init__(self, organization_slug, geocat_perma_link, geocat_perma_label, default_rights):
        self.geocat_perma_link = geocat_perma_link
        self.geocat_perma_label = geocat_perma_label
        self.organization_slug = organization_slug
        self.default_rights = default_rights
        self.dataset = {}
        g = rdflib.Graph()
        file = os.path.join(__location__, 'geocat-terms-of-use.ttl')
        g.parse(file, format='turtle')
        print("parsed g, len: {}".format(len(g)))

        #rights = _xpath_match_rights(rights_node, terms_of_use_graph)



    def process_geodata(self, csw_record_as_string, geocat_id):
        self.root = get_elem_tree_from_string(csw_record_as_string)
        self._set_dataset_publisher()
        self._process_dataset_identifier()
        self._process_dataset_frequency()
        self._process_dataset_title()
        self._set_dataset_description()
        self._set_dataset_issued()
        self._set_dataset_modified()
        self._set_dataset_contact_point()
        self._set_dataset_temporal()
        self._set_dataset_language()
        self._set_dataset_theme()
        self._set_dataset_coverage()
        self._set_dataset_see_alsos()
        self._set_dataset_spatial()
        self._set_dataset_keyword()

        dataset_rights = self._get_dataset_rights()
        self._get_download_distribution_formats()
        self._get_service_distribution_formats()

        self._process_resources(dataset_rights)

        self._add_geocat_permalink(geocat_id)
        self._add_owner_org()

        _print_dataset(self.dataset)
        return self.dataset

    def _process_dataset_identifier(self):
        GMD_IDENTIFIER = './/gmd:fileIdentifier/gco:CharacterString/text()'
        geocat_identifier = _xpath_get_single_sub_node_for_node_and_path(node=self.root, path=GMD_IDENTIFIER)
        self.dataset['identifier'] = str('@'.join([geocat_identifier, self.organization_slug]))

    def _process_dataset_frequency(self):
        GMD_ACRUAL_PERIDICITY = '//gmd:identificationInfo//che:CHE_MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode/@codeListValue'
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
        geocat_frequency = _xpath_get_single_sub_node_for_node_and_path(node=self.root, path=GMD_ACRUAL_PERIDICITY)
        accrual_periodicity = frequency_mapping.get(geocat_frequency)
        if accrual_periodicity:
            self.dataset['accrual_periodicity'] = accrual_periodicity
        else:
            self.dataset['accrual_periodicity'] = ''

    def _process_dataset_title(self):
        GMD_TITLE = '//gmd:identificationInfo//gmd:citation//gmd:title'
        title_node = _xpath_get_single_sub_node_for_node_and_path(node=self.root, path=GMD_TITLE)
        self.dataset['title'] = _xpath_get_language_dict_from_geocat_multilanguage_node(title_node)

    def _set_dataset_description(self):
        GMD_DESCRIPTION = '//gmd:identificationInfo//gmd:abstract'
        description_node = _xpath_get_single_sub_node_for_node_and_path(node=self.root, path=GMD_DESCRIPTION)
        self.dataset['description'] = _xpath_get_language_dict_from_geocat_multilanguage_node(description_node)

    def _set_dataset_issued(self):
        GMD_ISSUED = [
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "publication"]//gco:DateTime',
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "publication"]//gco:Date',
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "creation"]//gco:DateTime',
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "creation"]//gco:Date',
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:DateTime',
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date',
            ]
        geocat_issued = _xpath_get_first_of_values_from_path_list(node=self.root, path_list=GMD_ISSUED, get=XPATH_TEXT)
        if geocat_issued:
            self.dataset['issued'] = _map_to_ogdch_datetime(geocat_issued)

    def _set_dataset_modified(self):
        GMD_MODIFIED = [
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:DateTime',
            '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date',
        ]
        geocat_modified = _xpath_get_first_of_values_from_path_list(node=self.root, path_list=GMD_MODIFIED, get=XPATH_TEXT)
        if geocat_modified:
            self.dataset['modified'] = _map_to_ogdch_datetime(geocat_modified)
        else:
            self.dataset['modified'] = ''

    def _set_dataset_publisher(self):
        GMD_PUBLISHER = [
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "publisher"]//gmd:organisationName',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "owner"]//gmd:organisationName',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "pointOfContact"]//gmd:organisationName',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "distributor"]//gmd:organisationName',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "custodian"]//gmd:organisationName',
            '//gmd:contact//che:CHE_CI_ResponsibleParty//gmd:organisationName/gco:CharacterString',
        ]
        publisher_node = _xpath_get_first_of_values_from_path_list(node=self.root, path_list=GMD_PUBLISHER, get=XPATH_NODE)
        geocat_publisher = _xpath_get_one_value_from_geocat_multilanguage_node(publisher_node)
        if geocat_publisher:
            self.dataset['publishers'] = _map_to_ogdch_publishers(geocat_publisher)
        else:
            self.dataset['publishers'] = [{'label': ''}]

    def _set_dataset_contact_point(self):
        GMD_CONTACT_POINT = [
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "pointOfContact"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "owner"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "publisher"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "distributor"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
            '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "custodian"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
            '//gmd:contact//che:CHE_CI_ResponsibleParty//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
        ]
        geocat_contact_point = _xpath_get_first_of_values_from_path_list(node=self.root, path_list=GMD_CONTACT_POINT, get=XPATH_TEXT)
        if geocat_contact_point:
            self.dataset['contact_points'] = [{'name':geocat_contact_point, 'email': geocat_contact_point}]
        else:
            self.dataset['contact_points'] = []

    def _set_dataset_spatial(self):
        GMD_SPATIAL = '//gmd:identificationInfo//gmd:extent//gmd:description/gco:CharacterString/text()'
        geocat_spatial = _xpath_get_single_sub_node_for_node_and_path(node=self.root, path=GMD_SPATIAL)
        if geocat_spatial:
            self.dataset['spatial'] = geocat_spatial
        else:
            self.dataset['spatial'] = ''

    def _process_resources(self, dataset_rights):
        GMD_PROTOCOL = './/gmd:protocol/gco:CharacterString/text()'
        GMD_RESOURCES = '//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource'
        GMD_LANDING_PAGE_PROTOCOLS = ['WWW:LINK-1.0-http--link', 'WWW:LINK']
        GMD_RELATION_PROTOCOLS = ['WWW:LINK-1.0-http--link', 'WWW:LINK', 'CHTOPO:specialised-geoportal']
        GMD_RESOURCE_NAME = './/gmd:name/gco:CharacterString/text()'
        protocol_mapping = {
            "OGC:WMTS-http-get-capabilities": {'name': "WMTS (GetCapabilities)", "format": "service"},
            "OGC:WMS-http-get-map": "WMS (GetMap)",
            "OGC:WMS-http-get-capabilities": "WMS (GetCapabilities)",
            "OGC:WFS-http-get-capabilities": "WFS (GetCapabilities)",
            "WWW:DOWNLOAD-1.0-http--download": "Download",
            "WWW:DOWNLOAD-URL": "Download",
            "OGC:WMS": "WMS (GetMap)",
            "OGC:WFS": "WFS (GetCapabilities)",
            "OGC:WMTS": "WMTS (GetCapabilities)",
            "WWW:DOWNLOAD-FTP": "Download",
            "LINKED:DATA": "Linked Data Dienst"

        }
        self.dataset['relations'] = []
        self.dataset['resources'] = []
        resource_nodes = self.root.xpath(GMD_RESOURCES, namespaces=gmd_namespaces)
        for node in resource_nodes:
            protocol = _xpath_get_single_sub_node_for_node_and_path(node=node, path=GMD_PROTOCOL)
            print("-> processing protocol {}".format(protocol))
            if protocol in GMD_RELATION_PROTOCOLS:
                if not self.dataset.get('url') and protocol in GMD_LANDING_PAGE_PROTOCOLS:
                    self.dataset['url'] = _xpath_get_url_with_label_from_distribution(node).get('url')
                elif protocol in GMD_RELATION_PROTOCOLS:
                    url = _xpath_get_url_with_label_from_distribution(node)
                    self.dataset['relations'].append(url)
            else:
                if protocol.startswith("WWW:DOWNLOAD:"):
                    format = protocol.split(':')[-1]
                    # try to find format

                resource =  {}
                resource['description'] = _xpath_get_language_dict_from_geocat_multilanguage_node(node)
                resource['issued'] = self.dataset['issued']
                resource['modified'] = self.dataset['modified']
                resource['rights'] = dataset_rights
                protocol_title = protocol_title_mapping.get(protocol, None)
                resource_name = _xpath_get_single_sub_node_for_node_and_path(node=node, path=GMD_RESOURCE_NAME)
                resource['title'] = _map_to_ogdch_resource_title(
                    protocol_title=protocol_title,
                    resource_name=resource_name,
                    resource_description=resource['description'])
                resource['language'] = ['de']
                resource['format'] = ''
                resource['url'] = ''
                resource['download_url'] = ''

                resource['license'] = ''
                resource['byte_size'] = ''
                resource['identifier'] = ''
                resource['coverage'] = ''
                self.dataset['resources'].append(resource)
        self.dataset['resources'] = []

    def _set_dataset_coverage(self):
        """not implemented"""
        self.dataset['coverage'] = ''

    def _set_dataset_temporal(self):
        """not yet implemented"""
        GMD_TEMPORAL_START = '//gmd:identificationInfo//gmd:extent//gmd:temporalElement//gml:TimePeriod/gml:beginPosition/text()'
        GMD_TEMPORAL_END = '//gmd:identificationInfo//gmd:extent//gmd:temporalElement//gml:TimePeriod/gml:endPosition/text()'
        self.dataset['temporals'] = []

    def _set_dataset_language(self):
        """only one language is taken and set for the dataset
        TODO: can that be right? Shouldn't there be more languages taken?
        """
        GMD_LANGUAGE = ['//gmd:identificationInfo//gmd:language/gco:CharacterString/text()',
                        '//gmd:language/gmd:LanguageCode/@codeListValue']
        language_mapping = {
            'ger': 'de',
            'fra': 'fr',
            'eng': 'en',
            'ita': 'it',
        }
        geocat_languages = _xpath_get_all_values_for_node_and_path_list(node=self.root, path_list=GMD_LANGUAGE)
        self.dataset['language'] = []
        if geocat_languages:
            for geocat_language in set(geocat_languages):
                ogdch_language = language_mapping.get(geocat_language)
                if ogdch_language:
                    self.dataset['language'].append(ogdch_language)


    def _set_dataset_keyword(self):
        GMD_KEYWORDS = '//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword'
        keyword_nodes = self.root.xpath(GMD_KEYWORDS, namespaces=gmd_namespaces)
        geocat_keywords = []
        for node in keyword_nodes:
            keyword_dict = _xpath_get_language_dict_from_geocat_multilanguage_node(node)
            geocat_keywords.append(keyword_dict)
        self.dataset['keywords'] = _map_to_ogdch_keywords(geocat_keywords)

    def _set_dataset_see_alsos(self):
        GMD_SEE_ALSOS = '//gmd:identificationInfo//gmd:aggregationInfo//gmd:aggregateDataSetIdentifier/gmd:MD_Identifier/gmd:code/gco:CharacterString/text()'
        see_also_nodes = self.root.xpath(GMD_SEE_ALSOS, namespaces=gmd_namespaces)

    def _set_dataset_theme(self):
        GMD_THEME = '//gmd:identificationInfo//gmd:topicCategory/gmd:MD_TopicCategoryCode/text()'
        theme_mapping = {
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
        geocat_categories = _xpath_get_all_sub_nodes_for_node_and_path(node=self.root, path=GMD_THEME)
        if geocat_categories:
            ogdch_groups = []
            for category in geocat_categories:
                ogdch_groups.extend(theme_mapping.get(category))
            ogdch_groups = set(ogdch_groups)
            if ogdch_groups:
                self.dataset['groups'] = [{'name': group} for group in ogdch_groups]

    def _add_geocat_permalink(self, geocat_id):
        permalink = self.geocat_perma_link + geocat_id
        self.dataset['relations'].append({'url':permalink, 'label': self.geocat_perma_label})

    def _add_owner_org(self):
        self.dataset['owner_org'] = self.organization_slug

    def _get_dataset_rights(self):
        GMD_RIGHTS = './/gmd:resourceConstraints//gmd:otherConstraints'
        rights_node = _xpath_get_single_sub_node_for_node_and_path(node=self.root, path=GMD_RIGHTS)
        return self.default_rights

    def _get_download_distribution_formats(self):
        GMD_DOWNLOAD_FORMATS = ['//gmd:distributionInfo//gmd:distributionFormat//gmd:name//gco:CharacterString/text()']
        self.download_formats = _xpath_get_all_values_for_node_and_path_list(node=self.root, path_list=GMD_DOWNLOAD_FORMATS)

    def _get_service_distribution_formats(self):
        GMD_SERVICE_FORMATS = ['//gmd:identificationInfo//srv:serviceType/gco:LocalName/text()']
        self.formats = _xpath_get_all_values_for_node_and_path_list(node=self.root, path_list=GMD_SERVICE_FORMATS)


def _xpath_get_single_sub_node_for_node_and_path(node, path):
    results = node.xpath(path, namespaces=gmd_namespaces)
    if results:
        return results[0]
    else:
        return ''


def _xpath_get_all_sub_nodes_for_node_and_path(node, path):
    results = node.xpath(path, namespaces=gmd_namespaces)
    if results:
        return results
    else:
        return []


def _xpath_get_all_values_for_node_and_path_list(node, path_list):
    values = []
    for path in path_list:
        value = node.xpath(path, namespaces=gmd_namespaces)
        if value:
            values.extend(value)
    return values


def _xpath_get_first_of_values_from_path_list(node, path_list, get=XPATH_NODE):
    get_text = ''
    if get == XPATH_TEXT:
        get_text='/text()'
    for path in path_list:
        value = node.xpath(path + get_text, namespaces=gmd_namespaces)
        if value:
            return value[0]


def _xpath_get_language_dict_from_geocat_multilanguage_node(node):
    """
    get language dict as value
    """
    language_dict = {'en': '', 'it': '', 'de': '', 'fr': ''}
    try:
        for locale in LOCALES:
            value_locale = node.xpath('.//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#{}"]'.format(locale) + '/text()',
                           namespaces=gmd_namespaces)
            if value_locale:
                language_dict[locale.lower()] = _clean_string(value_locale[0])
        return language_dict
    except:
        value = node.xpath('.//gmd:CharacterString/text()',
            namespaces=gmd_namespaces)
        return value


def _xpath_match_rights(node, term_of_use_graph):
    open_license_refs = [
        'https://opendata.swiss/en/terms-of-use//#terms_open',
        'https://opendata.swiss/en/terms-of-use//#terms_by',
        'https://opendata.swiss/en/terms-of-use//#terms_ask',
        'https://opendata.swiss/en/terms-of-use//#terms_by_ask',
    ]
    rights_dict = {'en': '', 'it': '', 'de': '', 'fr': '', 'anchor': ''}
    try:
        anchor = node.xpath('.//gmx:Anchor/text()', namespaces=gmd_namespaces)
        if anchor:
            rights_dict['anchor'] = anchor[0]
        for locale in LOCALES:
            value_locale = node.xpath('.//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#{}"]'.format(locale) + '/text()',
                           namespaces=gmd_namespaces)
            if value_locale:
                rights_dict[locale.lower()] = _clean_string(value_locale[0])
    except:
        return ''


def _xpath_get_one_value_from_geocat_multilanguage_node(node):
    """
    get single value from multiple languages
    """
    value = node.xpath('.//gmd:CharacterString/text()',
        namespaces=gmd_namespaces)
    if value:
        return value
    for locale in LOCALES:
        value_locale = node.xpath('.//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#{}"]'.format(locale) + '/text()',
                       namespaces=gmd_namespaces)
        if value_locale:
            return value_locale


def _xpath_get_url_with_label_from_distribution(node):
    url = {}
    url_node = node.xpath('.//gmd:linkage/gmd:URL/text()',
        namespaces=gmd_namespaces)
    if url_node:
        url = {'label': url_node[0], 'url': url_node[0]}
    text_node = node.xpath('.//gmd:description',
        namespaces=gmd_namespaces)
    if text_node:
        url_text_node = _xpath_get_one_value_from_geocat_multilanguage_node(text_node[0])
        if url_text_node:
            url['label'] = url_text_node[0]
    return url


def _clean_string(value):
    return re.sub('\s+',' ',value).strip()


def _map_to_ogdch_datetime(datetime_value):
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


def _map_to_ogdch_publishers(geocat_publisher):
    dataset_publishers = []
    for publisher in geocat_publisher:
        dataset_publishers.append({'label': publisher})
    return dataset_publishers


def _map_to_ogdch_keywords(geocat_keywords):
    ogdch_keywords = {'fr': [], 'de': [], 'en': [], 'it': []}
    for keyword in geocat_keywords:
        for lang, geocat_keyword in keyword.items():
            if geocat_keyword != 'opendata.swiss' and lang in ['fr', 'de', 'en', 'it']:
                ogdch_keywords[lang].append(munge_tag(geocat_keyword))
    return ogdch_keywords


def _map_to_ogdch_resource_title(protocol_title=None, resource_name=None, resource_description=''):
    title_components = []
    if protocol_title:
        title_components.append(protocol_title)
    if resource_name:
        title_components.append(resource_name)
    title = " ".join(title_components)
    if title:
        multilanguage_title = {
            "de": title,
            "fr": title,
            "it": title,
            "en": title,
        }
    else:
        multilanguage_title = resource_description
    return multilanguage_title


def _print_dataset(dataset):
    print("\n==================== Result============================\n")
    for k, v in dataset.items():
        print("---------- {}".format(k))
        print(v)
