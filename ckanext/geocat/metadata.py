from lxml import etree
from collections import defaultdict
from owslib.csw import CatalogueServiceWeb
from owslib import util
import owslib.iso as iso
import logging
from ckan.lib.munge import munge_title_to_name
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
        return xml.xpath(xpath, namespaces=namespaces)[0]

    def get_value(self, **kwargs):
        self.env.update(kwargs)
        xml = self.env['xml']

        xpath = self._config
        log.debug("XPath: %s" % (xpath))

        try:
            # this should probably return a XPathTextValue
            value = self.get_element(xml, xpath)
        except Exception:
            log.debug('XPath not found: %s' % xpath)
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
            log.debug("Metadata key: %s" % key)
            attribute = self.get_attribute(key)
            dcat_metadata[key] = attribute.get_value(
                xml=meta_xml
            )
        return dcat_metadata


class GeocatDcatDatasetMetadata(DcatMetadata):
    """ Provides access to the Geocat metadata """
    def __init__(self):
        super(GeocatDcatDatasetMetadata, self).__init__()
        self.csw = CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')
        self.dist = GeocatDcatDistributionMetadata()

    def get_metadata(self):
        for xml_elem, value in self.csw.get_by_search(cql="csw:AnyText Like '%Eisenbahn%'"):
            log.debug("VALUE: %s" % value)
            dataset = self.load(xml_elem)
            dataset['resources'] = list(self.dist.get_metadata(xml_elem))
            yield dataset

    def get_mapping(self):
        return {
            'identifier': XPathTextValue('//gmd:fileIdentifier/gco:CharacterString'),  # noqa
            'title': StringValue(''),
            'description': StringValue(''),
            'issued': StringValue(''),
            'modified': StringValue(''),
            'publisher': StringValue(''),
            'contactPoint': StringValue(''),
            'theme': StringValue(''),
            'language': StringValue(''),
            'relation': StringValue(''),
            'keyword': StringValue(''),
            'landingPage': StringValue(''),
            'spatial': StringValue(''),
            'coverage': StringValue(''),
            'temporal': StringValue(''),
            'accrualPeriodicity': StringValue(''),
            'seeAlso': StringValue(''),
        }


class GeocatDcatDistributionMetadata(DcatMetadata):
    """ Provides access to the Geocat metadata """
    def __init__(self):
        super(GeocatDcatDistributionMetadata, self).__init__()
        self.csw = CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')

    def get_metadata(self, xml_elem):
        distributions = self.load(xml_elem)
        yield distributions


    def get_metadata_keys(self):
        return [
            'title',
            'description',
            'language',
            'issued',
            'modified',
            'accessURL',
            'rights',
            'license',
            'identifier',
            'downloadURL',
            'byteSize',
            'mediaType',
            'format',
            'coverage',
        ]
    
    def get_mapping(self):
        return {
            'title': StringValue(''),
            'description': StringValue(''),
            'language': StringValue(''),
            'issued': StringValue(''),
            'modified': StringValue(''),
            'accessURL': StringValue(''),
            'rights': StringValue(''),
            'license': StringValue(''),
            'identifier': StringValue(''),
            'downloadURL': StringValue(''),
            'byteSize': StringValue(''),
            'mediaType': StringValue(''),
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
    def __init__(self, url):
        self.catalog = GeocatCatalogueServiceWeb(url, skip_caps=True)
        self.schema = namespaces['che']

    def get_by_search(self, searchterm='', propertyname='csw:AnyText', cql=None):
        """ Returns the found csw dataset with the given searchterm """
        if cql is None:
            cql = "%s like '%%%s%%'" % (propertyname, searchterm)
        self.catalog.getrecords2(
            cql=cql,
            outputschema=self.schema
        )
        if self.catalog.response == None or self.catalog.results['matches'] == 0:
            raise DatasetNotFoundError("No dataset for the given searchterm '%s' (%s) found" % (searchterm, propertyname))
        # return a generator
        for id, value in self.catalog.records.iteritems():
            yield (self.catalog.xml_elem[id], value)

    def get_by_id(self, id):
        """ Returns the csw dataset with the given id """
        self.catalog.getrecordbyid(id=[id], outputschema=self.schema)
        return self.catalog.response

    def get_id_by_dataset_name(self, dataset_name):
        """ 
        Returns the id of a dataset identified by it's name.
        If there are multiple datasets with the given name,
        only the id of the first one is returned.
        """
        return self.get_by_search(dataset_name, 'title').itervalues().next().identifier


class DatasetNotFoundError(Exception):
    pass


class MappingNotFoundError(Exception):
    pass


class MetadataFormatError(Exception):
    pass
