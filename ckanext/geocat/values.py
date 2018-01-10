from lxml import etree
from ckan.lib.munge import munge_title_to_name
import ckanext.geocat.xml_loader as loader

import logging
log = logging.getLogger(__name__)


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
        result = loader.xpath(xml, xpath)
        if len(result) > 0:
            return result[0]
        return []

    def get_value(self, **kwargs):
        self.env.update({'empty_value': ''})
        self.env.update(kwargs)
        xml = self.env['xml']

        xpath = self._config
        log.debug("XPath: %s" % (xpath))

        try:
            value = self.get_element(xml, xpath)
        except etree.XPathError, e:
            log.debug('XPath not found: %s, error: %s' % (xpath, str(e)))
            value = ''

        if len(value) == 0 or value is None or not value:
            value = self.env['empty_value']
        return value


class XPathMultiValue(XPathValue):
    def get_element(self, xml, xpath):
        return loader.xpath(xml, xpath)


class XPathSubValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        sub_attributes = self.env.get('sub_attributes', [])
        value = []
        for xml_elem in loader.xpath(self.env['xml'], self._config):  # noqa
            sub_values = []
            kwargs['xml'] = xml_elem
            for sub in sub_attributes:
                sub_values.append(sub.get_value(**kwargs))
            value.append(sub_values)
        return value


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


class FirstInOrderValue(Value):
    def get_value(self, **kwargs):
        self.env.update({'empty_value': ''})
        self.env.update(kwargs)
        for attribute in self._config:
            value = attribute.get_value(**kwargs)
            if value:
                return value
        return self.env['empty_value']


class ArrayValue(Value):
    def get_value(self, **kwargs):
        self.env.update(kwargs)
        value = []
        for attribute in self._config:
            new_value = attribute.get_value(**kwargs)
            try:
                # only dig deeper, if the new_value is a sequence (e.g. a list)
                # otherwise simply add it to the resulting value
                if not is_sequence(new_value):
                    raise TypeError('%s is not a sequence' % new_value)
                iterator = iter(new_value)
                for inner_attribute in iterator:
                    if isinstance(inner_attribute, Value):
                        value.append(inner_attribute.get_value(**kwargs))
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


def is_sequence(arg):
    """
    this functions checks if the given argument
    is iterable (like a list or a tuple), but not
    a string
    """
    return (not hasattr(arg, "strip") and
            hasattr(arg, "__getitem__") or
            hasattr(arg, "__iter__"))
