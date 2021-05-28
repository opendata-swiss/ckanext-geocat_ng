# -*- coding: utf-8 -*-

import traceback

from urlparse import urljoin
from ckan.lib.helpers import json
from ckanext.harvest.model import HarvestObject, HarvestObjectExtra
from ckanext.harvest.harvesters import HarvesterBase
from ckanext.geocat_ng import csw_processor
from ckanext.geocat_ng import csw_mapping
from ckanext.geocat_ng import helpers
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

HARVEST_USER = 'harvest'
DEFAULT_RIGHTS = 'NonCommercialNotAllowed-CommercialNotAllowed-ReferenceRequired'
DEFAULT_PERMA_LINK = 'https://www.geocat.ch/geonetwork/srv/ger/md.viewer#/full_view/'
DEFAULT_PERMA_LINK_LABEL = 'geocat.ch Permalink'

class GeocatConfigError(Exception):
    pass


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

    def validate_config(self, config):
        if not config:
            return config
        try:
            config_obj = json.loads(config)
            if 'delete_missing_datasets' in config_obj:
                if not isinstance(config_obj['delete_missing_datasets'], bool):
                    raise ValueError('delete_missing_dataset must be boolean')
            if 'geocat_perma_link' not in config_obj:
                raise ValueError('permalink configuration is missing. Please provide the parameter "geocat_perma_link"'
                                 'The value can be derived from the harvester url: '
                                 'example: "geocat_perma_link":"https://www.geocat.ch/geonetwork/srv/ger/md.viewer#/full_view/"')
        except Exception as e:
            raise e
        return config

    def _set_config(self, config_str, source_id):
        if config_str:
            self.config = json.loads(config_str)
        else:
            self.config = {}
        self.config['user'] = self.config.get('user', HARVEST_USER)
        self.config['delete_missing_datasets'] = self.config.get('delete_missing_datasets', False)
        self.config['geocat_perma_link'] = self.config.get('geocat_perma_link', DEFAULT_PERMA_LINK)
        self.config['geocat_perma_label'] = tk.config.get('ckanext.geocat.permalink_title', DEFAULT_PERMA_LINK_LABEL)
        self.config['rights'] = self.config.get('rights', DEFAULT_RIGHTS)
        organization_slug = helpers.get_organization_slug_for_harvest_source(source_id)
        self.config['organization_slug'] = organization_slug
        self.config['legal_basis_url'] = self.config.get('legal_basis_url', None)
        log.error('Using config: %r', self.config)

    def gather_stage(self, harvest_job):
        log.debug('In GeocatHarvesterNG gather_stage')
        self._set_config(harvest_job.source.config, harvest_job.source.id)

        csw_url = harvest_job.source.url
        harvest_obj_ids = []

        csw_data = csw_processor.GeocatCatalogueServiceWeb(url=csw_url)
        gathered_geocat_identifiers = csw_data.get_geocat_id_from_csw()
        gathered_ogdch_identifier = ['@'.join([identifier, self.config['organization_slug']])
                                     for identifier in gathered_geocat_identifiers ]
        existing_dataset_infos = helpers.get_dataset_infos_for_organization(
            organization_name=self.config['organization_slug'],
            harvest_source_id=harvest_job.source_id
        )
        delete_packages = [(identifier, info) for identifier, info in existing_dataset_infos.items()
                            if info.belongs_to_harvester and identifier not in gathered_ogdch_identifier]

        csw_map = csw_mapping.GeodataRecordMapping(
            organization_slug=self.config['organization_slug'],
            geocat_perma_link=self.config['geocat_perma_link'],
            geocat_perma_label=self.config['geocat_perma_label'],
            default_rights=self.config['rights']
        )

        for geocat_id in gathered_geocat_identifiers:
            print("\n+++++++++++++++++++ processing {}\n".format(geocat_id))
            csw_record_as_string = csw_data.get_record_by_id(geocat_id)
            dataset_dict = csw_map.process_geodata(csw_record_as_string, geocat_id)
            obj = HarvestObject(guid=dataset_dict['identifier'], job=harvest_job,
                                content=json.dumps(dataset_dict))
            obj.save()
            harvest_obj_ids.append(obj.id)
        if self.config['delete_missing_datasets']:
            for identifier, info in delete_packages:
                obj = HarvestObject(guid=info.name, job=harvest_job,
                                    extras=[HarvestObjectExtra(key='import_action',
                                                               value='delete')])
                obj.save()
                harvest_obj_ids.append(obj.id)
        return harvest_obj_ids

    def fetch_stage(self, harvest_object):
        # Nothing to do here
        return True

    def import_stage(self, harvest_object):  # noqa
        log.debug('In GeocatHarvester import_stage')

        if not harvest_object:
            log.error('No harvest object received')
            self._save_object_error(
                'No harvest object received',
                harvest_object
            )
            return False

        # check if dataset must be deleted
        import_action = helpers.get_value_from_object_extra(harvest_object.extras, 'import_action')
        if import_action and import_action == 'delete':
            log.debug('import action: %s' % import_action)
            harvest_object.current = False
            return self._delete_dataset({'id': harvest_object.guid})

        try:
            pkg_dict = json.loads(harvest_object.content)
        except ValueError:
            self._save_object_error('Could not parse content for object {0}'.format(harvest_object.id),
                                    harvest_object, 'Import')
            return False

        flat_title = _derive_flat_title(pkg_dict['title'])
        if not flat_title:
            self._save_object_error('Unable to derive name from title %s' % pkg_dict['title'],  # noqa
                                    harvest_object, 'Import')
            return False
        pkg_dict['name'] = self._gen_new_name(flat_title)  # noqa

        try:
            package_context = {
                'ignore_auth': True,
                'user': self.config['user'],
            }
            try:
                # Change default schema to ignore lists of dicts, which
                # are stored in the '__junk' field
                schema = default_update_package_schema()
                schema['__junk'] = [ignore]

                package_context['schema'] = schema

                existing = self._find_existing_package(pkg_dict)
                log.debug(
                    "Existing package found, updating %s..." % existing['id']
                )
                pkg_dict['name'] = existing['name']
                pkg_dict['id'] = existing['id']
                updated_pkg = get_action('package_update')(
                    package_context, pkg_dict)
                harvest_object.current = True
                harvest_object.package_id = updated_pkg['id']
                harvest_object.save()
                log.debug("Updated PKG: %s" % updated_pkg)
            except NotFound:


                # Change default schema to ignore lists of dicts, which
                # are stored in the '__junk' field
                schema = default_create_package_schema()
                schema['__junk'] = [ignore]

                package_context['schema'] = schema

                log.debug("No package found, create a new one!")

                # generate an id to reference it in the harvest_object
                pkg_dict['id'] = unicode(uuid.uuid4())

                log.info('Package with GUID %s does not exist, '
                         'let\'s create it' % harvest_object.guid)

                harvest_object.current = True
                harvest_object.package_id = pkg_dict['id']
                harvest_object.add()

                model.Session.execute(
                    'SET CONSTRAINTS harvest_object_package_id_fkey DEFERRED')
                model.Session.flush()

                created_pkg = get_action('package_create')(
                    package_context, pkg_dict)

                log.debug("Created PKG: %s" % created_pkg)

            Session.commit()
            return True

        except Exception as e:
            self._save_object_error(
                ('Exception in import stage: %r / %s'
                    % (e, traceback.format_exc())
                ),
                harvest_object
            )
            return False


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


    def _delete_dataset(self, package_dict):
        log.debug('deleting dataset %s' % package_dict['id'])
        context = self._create_new_context()
        get_action('dataset_purge')(
            context.copy(),
            package_dict
        )
        return True

    def _create_new_context(self):
        # get the site user
        site_user = tk.get_action('get_site_user')(
            {'model': model, 'ignore_auth': True}, {})
        context = {
            'model': model,
            'session': Session,
            'user': site_user['name'],
        }
        return context

    def _process_csw(self, geocat_id):
        csw_record_as_string = csw_data.get_record_by_id(geocat_id)
        csw_map = csw_mapping.GeodataRecordMapping(
            csw_record_as_string=csw_record_as_string,
            organization_slug=self.config['organization_slug'],
            geocat_permalink=self.config['permalink_info'],
            default_rights = self.config['rights']
        )
        dataset_dict = csw_map.process_geodata()
        return dataset_dict


def _derive_flat_title(title_dict):
    """localizes language dict if no language is specified"""
    return title_dict.get('de') or title_dict.get('fr') or title_dict.get('en') or title_dict.get('it') or ""  # noqa
