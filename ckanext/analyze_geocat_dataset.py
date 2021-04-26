import click
from lxml import etree
import owslib
import re
from pprint import pprint
LOCALES = ['EN', 'FR', 'IT', 'DE']

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

GMD_IDENTIFIER = './/gmd:fileIdentifier'
GMD_TITLE = '//gmd:identificationInfo//gmd:citation//gmd:title'
GMD_DESCRIPTION = '//gmd:identificationInfo//gmd:abstract'
GMD_LANGUAGE = '//gmd:identificationInfo//gmd:language/gmd:LanguageCode'
GMD_ISSUED = ['//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "publication"]//gco:DateTime',
    '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "publication"]//gco:Date',
    '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "creation"]//gco:DateTime'
    '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "creation"]//gco:Date',
    '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:DateTime',
    '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date',
]
GMD_MODIFIED = [
    '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:DateTime',
    '//gmd:identificationInfo//gmd:citation//gmd:CI_Date[.//gmd:CI_DateTypeCode/@codeListValue = "revision"]//gco:Date',
]
GMD_PUBLISHER = [
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "publisher"]//gmd:organisationName',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "owner"]//gmd:organisationName',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "pointOfContact"]//gmd:organisationName',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "distributor"]//gmd:organisationName',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "custodian"]//gmd:organisationName',
    '//gmd:contact//che:CHE_CI_ResponsibleParty//gmd:organisationName/gco:CharacterString',
]
GMD_CONTACT_POINT = [
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "pointOfContact"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "owner"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "publisher"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "distributor"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
    '//gmd:identificationInfo//gmd:pointOfContact[.//gmd:CI_RoleCode/@codeListValue = "custodian"]//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
    '//gmd:contact//che:CHE_CI_ResponsibleParty//gmd:address//gmd:electronicMailAddress/gco:CharacterString',
]
GMD_LANDING_PAGE = [
'//gmd:distributionInfo/gmd:MD_Distribution//gmd:transferOptions//gmd:CI_OnlineResource',
'.//gmd:protocol/gco:CharacterString/text() = "WWW:LINK-1.0-http--link"]//che:LocalisedURL'
]
GMD_ACRUAL_PERIDICITY = '//gmd:identificationInfo//che:CHE_MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode/@codeListValue'
GMD_SPATIAL = '//gmd:identificationInfo//gmd:extent//gmd:description'
GMD_GET_TEXT = '/text()'
GMD_CHARACTER_STRING = '/gco:CharacterString'


def process_geodata(datafile):
    tree = etree.parse(datafile)
    root = tree.getroot()
    dataset = {}
    dataset['identifier'] = _get_single_node(root, path=GMD_IDENTIFIER, get_text=GMD_CHARACTER_STRING + GMD_GET_TEXT)
    dataset['accrual_periodicity'] = _get_single_node(root, path=GMD_ACRUAL_PERIDICITY, get_text="")
    title_node = _get_single_node(root, path=GMD_TITLE)
    dataset['title'] = _get_multilanguage_value(title_node)
    description_node = _get_single_node(root, path=GMD_DESCRIPTION)
    dataset['description'] = _get_multilanguage_value(description_node)
    dataset['issued'] = _get_first_of_values(root, path_list=GMD_ISSUED, get_text=GMD_GET_TEXT)
    dataset['modified'] = _get_first_of_values(root, path_list=GMD_MODIFIED, get_text=GMD_GET_TEXT)
    publisher_node = _get_first_of_values(root, path_list=GMD_PUBLISHER, get_text='')
    dataset['publisher'] = _get_multilanguage_value(publisher_node)
    dataset['contact_point'] = _get_first_of_values(root, path_list=GMD_CONTACT_POINT, get_text=GMD_GET_TEXT)
    dataset['spatial'] = _get_single_node(root, path=GMD_SPATIAL, get_text=GMD_CHARACTER_STRING + GMD_GET_TEXT)
    _print_dataset(dataset)


def _print_dataset(dataset):
    pprint(dataset)


def _get_single_node(root, path, get_text=""):
    results = root.xpath(path + get_text, namespaces=namespaces)
    if results:
        return results[0]
    else:
        return ''


def _get_multilanguage_value(node):
    """
    get title of a dataset
    """
    language_dict = {'en': '', 'it': '', 'de': '', 'fr': ''}
    try:
        for locale in LOCALES:
            value_locale = node.xpath('.//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#{}"]'.format(locale) + GMD_GET_TEXT,
                           namespaces=namespaces)
            if value_locale:
                language_dict[locale.lower()] = _clean_string(value_locale[0])
        return language_dict
    except:
        value = node.xpath('.//gmd:CharacterString' + GMD_GET_TEXT,
            namespaces=namespaces)
        return value


def _get_value_from_multilanguage_value(node):
    """
    get title of a dataset
    """
    language_dict = {'en': '', 'it': '', 'de': '', 'fr': ''}
    try:
        for locale in LOCALES:
            value_locale = node.xpath('.//gmd:textGroup/gmd:LocalisedCharacterString[@locale="#{}"]'.format(locale) + GMD_GET_TEXT,
                           namespaces=namespaces)
            if value_locale:
                language_dict[locale.lower()] = _clean_string(value_locale[0])
        return language_dict
    except:
        value = node.xpath('.//gmd:CharacterString' + GMD_GET_TEXT,
            namespaces=namespaces)
        return value




def _get_first_of_values(root, path_list, get_text=''):
    """
    get title of a dataset
    """
    for path in path_list:
        value = root.xpath(path + get_text, namespaces=namespaces)
        if value:
            return value[0]


def _clean_string(value):
    return re.sub('\s+',' ',value).strip()


@click.command()
@click.option('-d', '--datafile',
              help='Datafile to analyze')
def analyze_geodata(datafile=None):
    """This purges a ckan dataset:
This analyzes a datafile
"""
    if not datafile:
        raise click.UsageError("datafile is missing. Please provide a datafile -d")
    print("--------------- config ----------------")
    print("The datafile is {}".format(datafile))
    print("--------------- dataset ---------------")
    process_geodata(datafile=datafile)


if __name__ == '__main__':
    analyze_geodata()
