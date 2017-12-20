"""Tests for metadata """
import ckanext.geocat.metadata as metadata
from nose.tools import *  # noqa
import os
import sys
from datetime import datetime
import time

if sys.version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest

__location__ = os.path.realpath(
    os.path.join(
        os.getcwd(),
        os.path.dirname(__file__)
    )
)


class TestGeocatDcatDistributionMetadata(unittest.TestCase):
    def _load_xml(self, metadata, filename):
        path = os.path.join(__location__, 'fixtures', filename)
        with open(path) as xml:
            entry = metadata.get_metadata(xml.read())
        return entry

    def _is_multi_lang(self, value):
        for lang in ['de', 'fr', 'it', 'en']:
            self.assertIn(lang, value)

        
    def test_fields(self):
        dcat = metadata.GeocatDcatDistributionMetadata()
        distributions = self._load_xml(dcat, 'complete.xml')

        self.assertEquals(6, len(distributions))

        fields = [
            'identifier',
            'title',
            'description',
            'issued',
            'modified',
            'language',
            'url',
            'download_url',
            'license',
            'byte_size',
            'media_type',
            'format',
            'coverage',
        ]
        for dist in distributions:
            for field in fields:
                self.assertIn(field, dist)

            for key, value in dist.iteritems():
                self.assertIn(key, fields)

            # check multilang fields
            self._is_multi_lang(dist.get('title'))
            self._is_multi_lang(dist.get('description'))

    def test_fields_values(self):
        dcat = metadata.GeocatDcatDistributionMetadata()
        distributions = self._load_xml(dcat, 'complete.xml')

        download = None
        for dist in distributions:
            if dist['download_url']:
                download = dist
                break

        self.assertIsNotNone(download)

        # identifier
        self.assertEquals('', download.get('identifier'))

        # title
        self.assertEquals('Download', download['title']['de'])
        self.assertEquals('Download', download['title']['fr'])
        self.assertEquals('Download', download['title']['it'])
        self.assertEquals('Download', download['title']['en'])

        # description
        self.assertEquals('Download Server von geo.admin.ch', download['description']['de'])
        self.assertIn('', download['description']['fr'])
        self.assertIn('', download['description']['it'])
        self.assertIn('', download['description']['en'])

        # dates
        date_string = '2011-12-31' # revision date from XML
        d = datetime.strptime(date_string, '%Y-%m-%d')
        self.assertEquals(int(time.mktime(d.timetuple())), download['issued'])
        self.assertEquals(int(time.mktime(d.timetuple())), download['modified'])

        # language
        self.assertEquals(set(['de']), set(download.get('language')))

        # access url + download url
        self.assertEquals('http://data.geo.admin.ch/ch.bafu.laerm-bahnlaerm_nacht/data.zip', download.get('url'))
        self.assertEquals('http://data.geo.admin.ch/ch.bafu.laerm-bahnlaerm_nacht/data.zip', download.get('download_url'))
        self.assertEquals(download.get('url'), download.get('download_url'))

        # license
        self.assertEquals('', download.get('license'))

        # byte size
        self.assertEquals('', download.get('byte_size'))

        # media type
        self.assertEquals('application/zip', download.get('media_type'))

        # format
        self.assertEquals('', download.get('format'))

        # coverage
        self.assertEquals('', download.get('coverage'))
