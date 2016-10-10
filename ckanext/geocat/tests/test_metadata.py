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


class TestGeocatDcatDatasetMetadata(unittest.TestCase):
    def _load_xml(self, metadata, filename):
        path = os.path.join(__location__, 'fixtures', filename)
        with open(path) as xml:
            entry = metadata.get_metadata(xml.read())
        return entry

    def _is_multi_lang(self, value):
        for lang in ['de', 'fr', 'it', 'en']:
            self.assertIn(lang, value)

        
    def test_fields(self):
        dcat = metadata.GeocatDcatDatasetMetadata()
        dataset = self._load_xml(dcat, 'complete.xml')

        fields = [
            'id',
            'identifier',
            'title',
            'description',
            'issued',
            'modified',
            'publishers',
            'contact_points',
            'groups',
            'language',
            'relations',
            'temporals',
            'keywords',
            'url',
            'spatial',
            'coverage',
            'accrual_periodicity',
            'see_alsos',
        ]

        for field in fields:
	    self.assertIn(field, dataset)

        from pprint import pprint
        for key, value in dataset.iteritems():
            pprint(value) 
            self.assertIn(key, fields)

        # check multilang fields
        self._is_multi_lang(dataset.get('title'))
        self._is_multi_lang(dataset.get('description'))

    def test_fields_values(self):
        dcat = metadata.GeocatDcatDatasetMetadata()
        dataset = self._load_xml(dcat, 'complete.xml')

        # id
        self.assertEquals('', dataset.get('id'))

        # identifier
        self.assertEquals('93814e81-2466-4690-b54d-c1d958f1c3b8', dataset.get('identifier'))

        # title
        self.assertEquals(u'L\xe4rmbelastung durch Eisenbahnverkehr Nacht', dataset['title']['de'])
        self.assertEquals('Exposition au bruit du trafic ferroviaire, nuit', dataset['title']['fr'])
        self.assertEquals('Esposizione al rumore del traffico ferroviario, notte', dataset['title']['it'])
        self.assertEquals('Nighttime railway noise exposure', dataset['title']['en'])

        # description
        self.assertIn(u'Die Karte zeigt, welcher L\xe4rmbelastung', dataset['description']['de'])
        self.assertIn('', dataset['description']['fr'])
        self.assertIn('', dataset['description']['it'])
        self.assertIn('', dataset['description']['en'])

        # dates
        date_string = '2011-12-31' # revision date from XML
        d = datetime.strptime(date_string, '%Y-%m-%d')
        self.assertEquals(int(time.mktime(d.timetuple())), dataset['issued'])
        self.assertEquals(int(time.mktime(d.timetuple())), dataset['modified'])

        # publishers
        self.assertTrue(hasattr(dataset['publishers'], '__iter__'))
        self.assertEquals(1, len(dataset['publishers']))
        for publisher in dataset['publishers']:
            self.assertEquals(u'Bundesamt f\xfcr Umwelt', publisher['label'])

        # contact points
        self.assertTrue(hasattr(dataset['contact_points'], '__iter__'))
        self.assertEquals(1, len(dataset['contact_points']))
        for contact_point in dataset['contact_points']:
            self.assertEquals('noise@bafu.admin.ch', contact_point['name'])
            self.assertEquals('noise@bafu.admin.ch', contact_point['email'])

        # groups
        groups = ['territory', 'geography']
        for group in dataset.get('groups'):
            self.assertIn(group['name'], groups)

        # language
        self.assertEquals(set(['de']), set(dataset.get('language')))

        # relations
        self.assertTrue(hasattr(dataset['relations'], '__iter__'))
        self.assertEquals(1, len(dataset['relations']))
        for relation in dataset['relations']:
            self.assertIsNotNone(relation['label'])
            self.assertIsNotNone(relation['url'])

        # temporals
        self.assertTrue(hasattr(dataset['temporals'], '__iter__'))
        self.assertEquals(0, len(dataset['temporals']))

        # keywords
        keywords = {
            'de': [
                'larmbekampfung',
                'larmbelastung',
                'larmpegel',
                'larmimmission',
                'verkehrslarm',
                'larmwirkung',
                'gesundheit-und-sicherheit',
                'e-geoch-geoportal'
            ],
            'fr': [
                'impact-du-bruit',
                'effet-du-bruit',
                'diminution-du-bruit',
                'niveau-sonore',
                'polluant-sonore',
                'sante-et-securite-des-personnes',
                'geoportail-e-geoch',
                'bruit-routier',
            ],
            'it': [
                'livello-del-rumore',
                'inquinante-acustico',
                'rumore-del-traffico',
                'effetto-del-rumore',
                'geoportale-e-geoch',
                'abbattimento-del-rumore',
                'salute-umana-e-sicurezza',
                'immissione-di-rumore',
            ],
            'en': [
                'noise-pollutant',
                'noise-level',
                'noise-abatement',
                'noise-immission',
                'human-health-and-safety',
                'traffic-noise',
                'noise-effect',
                'e-geoch-geoportal',
            ],
        }
        for lang in ['de', 'fr', 'it', 'en']:
            self.assertEquals(set(keywords[lang]), set(dataset['keywords'][lang]))

        # url
        self.assertEquals('http://www.bafu.admin.ch/laerm/', dataset.get('url'))

        # spatial
        self.assertEquals('Schweiz', dataset.get('spatial'))

        # coverage
        self.assertEquals('', dataset.get('coverage'))

        # accrual periodicity
        self.assertEquals('', dataset.get('accrual_periodicity'))

        # see alsos
        self.assertTrue(hasattr(dataset['see_alsos'], '__iter__'))
        self.assertEquals(0, len(dataset['see_alsos']))
