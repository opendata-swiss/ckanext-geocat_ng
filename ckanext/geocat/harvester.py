# -*- coding: utf-8 -*-

import requests
import traceback

from ckan.lib.helpers import json
from ckan.lib.munge import munge_tag
from ckanext.harvest.model import HarvestObject
from ckanext.harvest.harvesters import HarvesterBase
import ckanext.geocat.metadata as md 

from pylons import config

import logging
log = logging.getLogger(__name__)


class GeocatHarvester(HarvesterBase):
    '''
    The harvester for geocat
    '''

    HARVEST_USER = 'harvest'

    def info(self):
        return {
            'name': 'geocat_harvester',
            'title': 'Geocat harvester',
            'description': (
                'Harvests metadata from geocat (CSW)'
            ),
            'form_config_interface': 'Text'
        }

    def _set_config(self, config_str):
        if config_str:
            self.config = json.loads(config_str)
        else:
            self.config = {}

        if 'user' not in self.config:
            self.config['user'] = self.HARVEST_USER

        if 'organization' not in self.config or not self.config.get('organization', None):
            raise GeocatConfigError("Provide a config value for 'organization'")

        log.debug('Using config: %r' % self.config)

    def gather_stage(self, harvest_job):
        log.debug('In GeocatHarvester gather_stage')
        api_url = None

        try:
            self._set_config(harvest_job.source.config)
        except GeocatConfigError, e:
            self._save_gather_error(
                'Config value missing: %s' % str(e),
                harvest_job
            )
            return False

        try:
            harvest_obj_ids = []
            csw = md.CswHelper()

            for record in csw.get_by_search('XY'):
                harvest_obj = HarvestObject(
                    guid=record['identifier'],
                    job=harvest_job
                )
                harvest_obj.save()
                harvest_obj_ids.append(harvest_obj.id)

            log.debug('IDs: %r' % harvest_obj_ids)

            return harvest_obj_ids
        except Exception, e:
            self._save_gather_error(
                'Unable to get content for URL: %s: %s / %s'
                % (base_url, str(e), traceback.format_exc()),
                harvest_job
            )

    def fetch_stage(self, harvest_object):
        log.debug('In GeocatHarvester fetch_stage')
        self._set_config(harvest_object.job.source.config)

        if not harvest_object:
            log.error('No harvest object received')
            self._save_object_error(
                'No harvest object received',
                harvest_object
            )
            return False

        base_url = harvest_object.source.url.rstrip('/')
        try:
            csw = md.CswHelper()
            xml = csw.get_by_id('xy')
            harvest_object.content = xml
            harvest_object.save()
            log.debug('successfully processed ' + harvest_object.guid)
            return True
        except Exception, e:
            self._save_object_error(
                (
                    'Unable to get content for package: %s: %r / %s'
                    % (api_url, e, traceback.format_exc())
                ),
                harvest_object
            )
            return False

    def import_stage(self, harvest_object):
        log.debug('In GeocatHarvester import_stage')
        self._set_config(harvest_object.job.source.config)

        if not harvest_object:
            log.error('No harvest object received')
            self._save_object_error(
                'No harvest object received',
                harvest_object
            )
            return False

        try:
            dataset_metadata = md.GeocatDcatDatasetMetadata()
            pkg_dict = dataset_metadata.load(harvest_object.content)
            pkg_dict['identifier'] = pkg_dict['identifier'] + '@' + self.config.get('organization', '')

            dist_metadata = md.GeocatDcatDistributionMetadata()
            pkg_dict['distribution'] = dist_metadata.load(harvest_object.content)

            log.debug('package dict: %s' % pkg_dict)
            return self._create_or_update_package(pkg_dict, harvest_object)
        except Exception, e:
            self._save_object_error(
                (
                    'Exception in import stage: %r / %s'
                    % (e, traceback.format_exc())
                ),
                harvest_object
            )
            return False

class GeocatConfigError(Exception):
    pass
