# -*- coding: utf-8 -*-

import traceback

from urlparse import urljoin
from ckan.lib.helpers import json
from ckanext.harvest.model import HarvestObject, HarvestObjectExtra
from ckanext.harvest.harvesters import HarvesterBase
from ckanext.geocat_ng import csw_processor
from ckanext.geocat_ng.csw_mapping import process_geodata
from ckan.logic import get_action, NotFound
from ckan.logic.schema import default_update_package_schema,\
    default_create_package_schema
from ckan.lib.navl.validators import ignore
import ckan.plugins.toolkit as tk
from ckan import model
from ckan.model import Session
import uuid

import logging
log = logging.getLogger(__name__)


class GeocatNGHarvester(HarvesterBase):
    '''
    The harvester for geocat
    '''
    HARVEST_USER = 'harvest'

    def info(self):
        return {
            'name': 'geocat_ng_harvester',
            'title': 'Geocat NG harvester',
            'description': (
                'Harvests metadata from geocat (CSW) NG (refactored)'
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

        if 'delete_missing_datasets' not in self.config:
            self.config['delete_missing_datasets'] = False

        # get config for geocat permalink
        self.config['permalink_url'] = tk.config.get('ckanext.geocat.permalink_url', None) # noqa
        self.config['permalink_bookmark'] = tk.config.get('ckanext.geocat.permalink_bookmark', None) # noqa
        self.config['permalink_title'] = tk.config.get('ckanext.geocat.permalink_title', 'geocat.ch Permalink') # noqa
        self.config['permalink_valid'] = self.config['permalink_url'] and self.config['permalink_bookmark'] # noqa

        log.debug('Using config: %r' % self.config)

    def _find_existing_package(self, package_dict):
        package_show_context = {'model': model, 'session': Session,
                                'ignore_auth': True}

        user = tk.get_action('get_site_user')({'ignore_auth': True}, {})
        package_show_context.update({'user': user['name']})

        param = 'identifier:%s' % package_dict['identifier']
        result = tk.get_action('package_search')(package_show_context,
                                                 {'fq': param})
        try:
            return result['results'][0]
        except (KeyError, IndexError, TypeError):
            raise NotFound

    def gather_stage(self, harvest_job):
        log.error("NEW ======================================================")
        log.debug('In GeocatHarvester gather_stage')

        try:
            self._set_config(harvest_job.source.config)
            if 'organization' not in self.config:
                context = {
                    'model': model,
                    'session': Session,
                    'ignore_auth': True
                }
                source_dataset = get_action('package_show')(
                    context, {'id': harvest_job.source_id})
                self.config['organization'] = source_dataset.get(
                    'organization').get('name')
        except GeocatConfigError, e:
            self._save_gather_error(
                'Config value missing: %s' % str(e),
                harvest_job
            )
            return []

        csw_url = None
        harvest_obj_ids = []
        csw_url = harvest_job.source.url
        csw = csw_processor.GeocatCatalogueServiceWeb(url=csw_url)
        gathered_geocat_identifiers = csw.get_geocat_id_from_csw()
        log.error(gathered_geocat_identifiers)

        for geocat_id in gathered_geocat_identifiers:
            csw_record = csw.get_record_by_id(geocat_id)

        return harvest_obj_ids

    def fetch_stage(self, harvest_object):
        log.debug('In GeocatHarvester fetch_stage')
        return False

    def import_stage(self, harvest_object):  # noqa
        log.debug('In GeocatHarvester import_stage')
        return False


class GeocatConfigError(Exception):
    pass
