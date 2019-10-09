# -*- coding: utf-8 -*-

import httpretty
import nose
import os

import ckantoolkit.tests.helpers as h

import ckanext.harvest.model as harvest_model
from ckanext.harvest import queue

from ckanext.geocat.metadata import CswHelper


eq_ = nose.tools.eq_
assert_true = nose.tools.assert_true
assert_raises = nose.tools.assert_raises

__location__ = os.path.realpath(
    os.path.join(
        os.getcwd(),
        os.path.dirname(__file__)
    )
)

mock_url = "http://mock-geocat.ch"

# Monkey patch required because of a bug between httpretty and redis.
# See https://github.com/gabrielfalcao/HTTPretty/issues/113

original_get_id_by_search = CswHelper.get_id_by_search


def _patched_get_id_by_search(self, searchterm='', propertyname='csw:AnyText',
                              cql=None):
    httpretty.enable()

    for nextrecord in original_get_id_by_search(self, searchterm, propertyname, cql):
        yield nextrecord

    httpretty.disable()


CswHelper.get_id_by_search = _patched_get_id_by_search

original_get_by_id = CswHelper.get_by_id

def _patched_get_by_id(self, id):
    httpretty.enable()

    id = original_get_by_id(self, id)

    httpretty.disable()

    return id

CswHelper.get_by_id = _patched_get_by_id

# End monkey patch


class FunctionalHarvestTest(object):
    @classmethod
    def setup_class(cls):
        h.reset_db()

        cls.gather_consumer = queue.get_gather_consumer()
        cls.fetch_consumer = queue.get_fetch_consumer()

    def setup(self):
        harvest_model.setup()

        queue.purge_queues()

        user_dict = h.call_action('user_create', name='seanh',
                                  email='seanh@seanh.com', password='password')
        org_context = {
            'user': user_dict['name'],
            'return_id_only': True
        }
        org_data_dict = {
            'name': 'geocat_org'
        }
        self.org_id = h.call_action('organization_create',
                                org_context, **org_data_dict)

    def teardown(self):
        h.reset_db()

    def _create_harvest_source(self, **kwargs):
        source_dict = {
            'title': 'Geocat harvester',
            'name': 'geocat-harvester',
            'url': mock_url,
            'source_type': 'geocat_harvester',
            'owner_org': self.org_id
        }

        source_dict.update(**kwargs)

        harvest_source = h.call_action('harvest_source_create',
                                       {}, **source_dict)

        return harvest_source

    def _update_harvest_source(self, **kwargs):

        source_dict = {
            'title': 'Geocat harvester',
            'name': 'geocat-harvester',
            'url': 'http://geocat',
            'source_type': 'geocat_harvester',
            'owner_org': self.org_id
        }

        source_dict.update(**kwargs)

        harvest_source = h.call_action('harvest_source_update',
                                       {}, **source_dict)

        return harvest_source

    def _create_harvest_job(self, harvest_source_id):

        harvest_job = h.call_action('harvest_job_create',
                                    {}, source_id=harvest_source_id)

        return harvest_job

    def _run_jobs(self, harvest_source_id=None):
        try:
            h.call_action('harvest_jobs_run',
                          {}, source_id=harvest_source_id)
        except Exception, e:
            if str(e) == 'There are no new harvesting jobs':
                pass

    def _gather_queue(self, num_jobs=1):

        for job in xrange(num_jobs):
            # Pop one item off the queue (the job id) and run the callback
            reply = self.gather_consumer.basic_get(
                queue='ckan.harvest.gather.test')

            # Make sure something was sent to the gather queue
            assert reply[2], 'Empty gather queue'

            # Send the item to the gather callback, which will call the
            # harvester gather_stage
            queue.gather_callback(self.gather_consumer, *reply)

    def _fetch_queue(self, num_objects=1):

        for _object in xrange(num_objects):
            # Pop item from the fetch queues (object ids) and run the callback,
            # one for each object created
            reply = self.fetch_consumer.basic_get(
                queue='ckan.harvest.fetch.test')

            # Make sure something was sent to the fetch queue
            assert reply[2], 'Empty fetch queue, the gather stage failed'

            # Send the item to the fetch callback, which will call the
            # harvester fetch_stage and import_stage
            queue.fetch_callback(self.fetch_consumer, *reply)

    def _run_full_job(self, harvest_source_id, num_jobs=1, num_objects=1):
        # Create new job for the source
        self._create_harvest_job(harvest_source_id)

        # Run the job
        self._run_jobs(harvest_source_id)

        # Handle the gather queue
        self._gather_queue(num_jobs)

        # Handle the fetch queue
        self._fetch_queue(num_objects)


class TestGeocatHarvestFunctional(FunctionalHarvestTest):
    def _test_harvest_create(self, url, all_results, single_result, num_objects, **kwargs):
        # Mock the CSW requests
        httpretty.register_uri(httpretty.POST, url, body=all_results)
        httpretty.register_uri(httpretty.GET, url, body=single_result)

        harvest_source = self._create_harvest_source(**kwargs)

        self._run_full_job(harvest_source['id'], num_objects=num_objects)

        # Check that correct amount of datasets were created
        fq = "+type:dataset harvest_source_id:{0}".format(harvest_source['id'])
        results = h.call_action('package_search', {}, fq=fq)
        eq_(results['count'], num_objects)
        return results

    def test_harvest_create_simple(self):
        path = os.path.join(__location__, 'fixtures', 'all_results_response.xml')
        with open(path) as xml:
            all_results = xml.read()

        path = os.path.join(__location__, 'fixtures', 'single_result_response.xml')
        with open(path) as xml:
            single_result = xml.read()

        results = self._test_harvest_create(mock_url, all_results, single_result, 1)
