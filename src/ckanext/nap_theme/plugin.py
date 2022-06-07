import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckan.lib.base as base
import ckan.lib.navl.dictization_functions as df
import ckan.lib.helpers as h
import re
import ipaddress
import json
import codecs
import os
from ckan.common import _, request
from flask import Blueprint
from ckan import logic
from ckan import model
from urllib.request import urlopen, URLError
from flask.templating import render_template
from datetime import date, datetime
from ckan.views.user import RequestResetView
from six import text_type
from notifications_python_client.notifications import NotificationsAPIClient
from ckan.common import config

# GovNotify API Key
notify_api_key = config.get('ckanext.nap_theme.gov_notify_key', None)
notifications_client = NotificationsAPIClient(notify_api_key)

# Feature flags
reset_password_flag = config.get('ckanext.nap_theme.reset_password_feature_flag', False)

create_account_flag = config.get('ckanext.nap_theme.create_account_feature_flag', False)


def get_reset_password_feature_flag():
    return toolkit.asbool(reset_password_flag)

def get_create_account_flag():
    return toolkit.asbool(create_account_flag)

Invalid = df.Invalid
c= base.c

# custom templates
def cookies():
    return render_template(u'cookies.html')

def application_submitted():
    return render_template(u'user/application_submitted.html')

def check_if_admin():
    context = {'model': model, 'user': c.user, 'auth_user_obj': c.userobj}
    try:
        logic.check_access('sysadmin', context, {})
    except logic.NotAuthorized:
        base.abort(403, _('You need to be signed in as an administrator to access admin options'))
    return True

def admin_applications():
    check_if_admin()
    users = get_unauthorised_users()
    return toolkit.render(u'user/admin_applications.html', {u'users' : users})

def admin_approved():
    check_if_admin()
    users = get_approved_users()
    return toolkit.render(u'user/admin_approved.html', {u'users' : users})

def admin_rejected():
    check_if_admin()
    users = get_rejected_users()
    return toolkit.render(u'user/admin_rejected.html', {u'users' : users})

def admin_admins():
    check_if_admin()
    users = get_admin_users()
    return toolkit.render(u'user/admin_admins.html', {u'users' : users})

def _admin_get_user(id,view,error_summary={}):
    check_if_admin()
    try:
        data_dict = {u'id': id}
        user =  logic.get_action('user_show')({}, data_dict)
    except toolkit.ObjectNotFound:
        user =  None
    return toolkit.render(view, {u'user' : user, u'error_summary': error_summary})

def admin_approve_application(id=None, error_summary={}):
    return _admin_get_user(id, u'user/admin_approve_application.html', error_summary)

def admin_reject_application(id=None, error_summary={}):
    return _admin_get_user(id, u'user/admin_reject_application.html', error_summary)

def admin_application_approved(id=None):
    check_if_admin()
    # set about for user to empty and make user an editor of the organisation
    id = request.form['id']
    organization = request.form['organization']
    if organization == '':
        error_summary = {'organization' : 'You must select an organisation'}
        return admin_approve_application(id, error_summary)
    orgs = get_orgs()
    org = [org for org in orgs if org['id']==organization][0]
    data_dict = {u'id': id}
    user =  logic.get_action('user_show')({}, data_dict)
    user['about'] = ''
    user['image_url']=org['display_name']
    if user['email'] == '':
        user['email'] = f'{user["name"]}@localhost'
    pe = { 'nap_theme' : {
        'approved_on' : datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
        'approved_by' : c.user
    }}
    user['plugin_extras'] = pe
    user = logic.get_action('user_update')({}, user)
    # send email to user
    send_application_approved_email(user['email'], user['fullname'], user['name'])    
    # add user to organisation
    data_dict = {u'id': organization, u'username': user['name'], u'role':'editor'}
    logic.get_action('organization_member_create')({}, data_dict)
    return h.redirect_to(u'nap_theme.admin_approved')

def admin_application_rejected():
    check_if_admin()
    id = request.form['id']
    reject_message = request.form['reject_message']
    if reject_message == '':
        error_summary = {'reject-message' : 'You must provide a reject message'}
        return admin_reject_application(id, error_summary)

    # set about for user to 'rejected'
    data_dict = {u'id': id}
    user =  logic.get_action('user_show')({}, data_dict)
    user['about'] = 'rejected'
    if user['email'] == '':
        user['email'] = f'{user["name"]}@localhost'
    pe = { 'nap_theme' : {
        'reject_message' : reject_message,
        'rejected_on' : datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
        'rejected_by' : c.user
    }}
    user['plugin_extras'] = pe
    user = logic.get_action('user_update')({}, user)

    #send email to user
    send_application_rejected_email(user['email'], user['fullname'], reject_message)    

    return h.redirect_to(u'nap_theme.admin_rejected')

# delete user from admin pages
def admin_delete_user():
    check_if_admin()
    id = request.form['id']
    data_dict = {u'id': id}
    logic.get_action('user_delete')({}, data_dict)
    return_to = request.form['return_to']
    return_string = f'nap_theme.{return_to}'
    print(return_string)
    return h.redirect_to(return_string)

# gov notify functions
def send_application_submitted_email(user):
    email = user.email
    response = notifications_client.send_email_notification(
        email_address=email, # required string
        template_id='2dbb9dd7-938c-4887-8b56-5023cd491382', # required UUID string
        personalisation={
            'name': user.fullname,
        }        
    )
    return response

def send_application_approved_email(email, name, sign_in):

    response = notifications_client.send_email_notification(
        email_address=email, # required string
        template_id='971d0b66-3466-443f-8c94-422ea9950e18', # required UUID string
        personalisation={
            'name': name,
            'sign_in' : sign_in
        }        
    )
    return response

def send_application_rejected_email(email, name, reason):

    response = notifications_client.send_email_notification(
        email_address=email, # required string
        template_id='de30ebe1-b6d1-4830-b87a-f7d9fb474204', # required UUID string
        personalisation={
            'name': name,
            'reason' : reason
        }        
    )
    return response

def reset_password_link_email(email, name, reset_link):

    response = notifications_client.send_email_notification(
        email_address=email, # required string
        template_id='c093efd1-70c7-4242-a153-cab3b4b715aa', # required UUID string
        personalisation={
            'name': name,
            'reset_link' : reset_link
        }        
    )
    return response

# helper functions
def get_extra(package_extras, key):
    ''' Used for getting a specific package extras

    :param package_extras: the package extras
    :type package_extras: dict
    '''
    for extra in package_extras:
        if key == extra['key']:
            return extra['value']
    return None
    
def get_orgs():
    orgs = logic.get_action('organization_list')({}, {'all_fields': 'true','include_dataset_count': 'false'})
    return orgs

def get_tags():
    tags = logic.get_action('tag_list')({}, {'all_fields': 'true'})
    return tags

def get_tag_names(package_tags):
    tag_names = ','.join([tag['display_name'] for tag in package_tags])
    return tag_names

def get_sorted_error_summary(errorsDict):
    if errorsDict:
        # Sorted error summary message so they appear in the right order and strip off sorted order added in the custom validators
        sortedErrors = sorted(errorsDict.items(), key=lambda value: value[1] )
        sortedErrorsDict = dict(sortedErrors)
        # remove sorting number
        for k,v in sortedErrorsDict.items():
            sortedErrorsDict[k] = v.split('|')[1]
        return sortedErrorsDict
    else:
        return {}

def get_form_data(form_data, pkg_dict):
    #    Set initial value for all form values required
    blank_form_dict = {
        'owner_org' : '',
        'title' : '',
        'notes' : '',
        'url': 'http://',
        'tag_string': '',
        'license_id' : '',
        'version': '',
        'author': '',
        'author_email': '',
        'data_formats': '',
        'update_frequency': '',
        'location' : '',
        'regularly_updated': '',
        'date_range_latest': '',
        'date_range_earliest': '',
        'date_range_earliest_day': '',
        'date_range_earliest_month': '',
        'date_range_earliest_year': '',
        'date_range_latest_day': '',
        'date_range_latest_month': '',
        'date_range_latest_year': '',
        'regularly_updated_earliest_day': '',
        'regularly_updated_earliest_month': '',
        'regularly_updated_earliest_year': '',
        'description': '',
        'data_available': ''
    }
    # set value of form either blank if new, edit value or if an error the value entered by the user!
    for key in blank_form_dict.keys():
        if not key in form_data:
            if key in pkg_dict:
                # special case handling for tags!
                if (key == 'tag_string'):
                    form_data[key] = get_tag_names(pkg_dict.tags)
                else:
                    form_data[key] = pkg_dict[key]
            else:
                form_data[key] = blank_form_dict[key]
    form_data['date_range_earliest'] = f"{form_data['date_range_earliest_day']}/{form_data['date_range_earliest_month']}/{form_data['date_range_earliest_year']}"
    form_data['date_range_latest'] = f"{form_data['date_range_latest_day']}/{form_data['date_range_latest_month']}/{form_data['date_range_latest_year']}"
    return form_data

def get_package_display_name(display_name):
    if display_name == 'Dataset':
        display_name = 'All datasets'
    return display_name

# ==================================================== Custom validators ========================================================

# User validators
def custom_user_organisation_validator(key, data,error, context):
    value = data.get(key)
    if value == '':
        raise Invalid(_('2|Enter your organisation'))    

def custom_user_fullname_validator(key, data,error, context):
    value = data.get(key)
    if value == '':
        raise Invalid(_('1|Enter your name'))    

# Package validators
def is_valid_url_prefix(url):
    return url.startswith("http://") or url.startswith('https://')

def is_localhost(url):
    return url.startswith("http://localhost") or url.startswith('https://localhost')

def is_ip(url):
    url = url.replace("http://", "").replace("https://", "")
    parts = url.split(":")
    if len(parts) == 1:
         #no port
         url = parts[0].split("/")[0]
    else:
        url = parts[0]
    try:
        ip = ipaddress.ip_address(url)
        return True
    except:
        return False

def custom_url_validator(key, data, errors, context):
    data_available = data.get(('data_available',))
    general_response = _('2|Enter a dataset link that is a correct URL, like https://data.gov.uk/')
    if data_available == "yes":
        url = data.get(key, None)
        # parse input string rejecting anything that does not start with http:// or https:// and isnt localhost or an ip address domain
        if not is_valid_url_prefix(url):
            raise Invalid(_('2|Enter a dataset link URL that starts with http:// or https://'))
        if is_localhost(url):
            raise Invalid(general_response)
        if is_ip(url):
            raise Invalid(_('2|Enter a dataset link URL that the domain is not an IP address. IP address domains are not permitted. For example https://384.23.45.21/transport/dataset123 is not permitted but https://data.gov.uk/transport/data123 is.'))

        # Checks that the provided value is a valid URL and exists!
        try:
            urlopen(url)
            return
        except URLError:
            raise Invalid(_('2|Enter a dataset link URL that exists.'))
        except: 
            raise Invalid(general_response)
            

def custom_owner_org_validator(key, data, errors, context):
    value = data.get(key)
    if value == '':
        raise Invalid(_('1|Select a publisher'))

def custom_title_validator(key, data, errors, context):
    value = data.get(key)
    if value == '':
        raise Invalid(_('2|Enter a title'))

def custom_author_email_validator(value, context):
    email_pattern = re.compile(
                            # additional pattern to reject malformed dots usage
                            r"^(?!\.)(?!.*\.$)(?!.*?\.\.)"\
                            "[a-zA-Z0-9.!#$%&'*+\/=?^_`{|}~-]+@[a-zA-Z0-9]"\
                            "(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9]"\
                            "(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
                        )
    # validate email input 
    if value:
        if not email_pattern.match(value):
            raise Invalid(_('5|Enter a contact email in the correct format, like name@test.com'))
    return value

def custom_location_validator(key, data, errors, context):
    value = data.get(key)
    if value == '':
        raise Invalid(_('3|Enter the location this dataset was collected in'))

def custom_update_frequency_validator(key, data, errors, context):
    is_updated = data.get(('regularly_updated',))
    value = data.get(key)
    if is_updated == 'yes':
        if value == '':
            raise Invalid(_('4|Enter the update frequency of the dataset'))
    return value

def custom_description_validator(key, data, errors, context):
    value = data.get(key)
    if value == '':
        raise Invalid(_('5|Enter what this dataset measures'))

def custom_date_range_earliest_validator(key, data, errors, context):
    is_updated = data.get(('regularly_updated',))
    if is_updated == 'no':
        year = data.get(('date_range_earliest_year',))
        month = data.get(('date_range_earliest_month',))
        day = data.get(('date_range_earliest_day',))

        if year and month and year:
            try:
                date = datetime(int(year), int(month), int(day))
            except:
                 raise Invalid(_('6|Earliest date must be a real date'))
            now = datetime.now()
            if date > now:
                raise Invalid(_('6|Enter a earliest date that is in the past'))

def custom_date_range_latest_validator(key, data, errors, context):
    is_updated = data.get(('regularly_updated',))
    if is_updated == 'no':
        year = data.get(('date_range_latest_year',))
        month = data.get(('date_range_latest_month',))
        day = data.get(('date_range_latest_day',))

        if year and month and year:
            try:
                date = datetime(int(year), int(month), int(day))
            except:
                raise Invalid(_('5|Latest date must be a real date'))
            now = datetime.now()
            if date > now:
                raise Invalid(_('5|Enter a latest date that is in the past'))
            earliest_year = data.get(('date_range_earliest_year',))
            earliest_month = data.get(('date_range_earliest_month',))
            earliest_day = data.get(('date_range_earliest_day',))
            _custom_date_range_validator(year, month, day, earliest_year, earliest_month, earliest_day)

def _custom_date_range_validator(latest_year, latest_month, latest_day, earliest_year, earliest_month, earliest_day):
    if latest_year and latest_month and latest_year and earliest_year and earliest_month and earliest_day:
        try:
            latest_date = datetime(int(latest_year), int(latest_month), int(latest_day))
            earliest_date = datetime(int(earliest_year), int(earliest_month), int(earliest_day))
        except: 
            return
        if earliest_date > latest_date:
            raise Invalid(_('6|Enter a latest date that is after the earliest date'))

def _custom_date_field_validator(data, key):
    is_updated = data.get(('regularly_updated',))
    if is_updated == 'no':
        date = data.get(key)
        return (date == '')
    return False

def custom_latest_year_validator(key, data, errors, context):
    if _custom_date_field_validator(data, key):
        raise Invalid(_('8|The latest date must include a year'))

def custom_latest_month_validator(key, data, errors, context):
    if _custom_date_field_validator(data, key):
        raise Invalid(_('8|The latest date must include a month'))

def custom_latest_day_validator(key, data, errors, context):
    if _custom_date_field_validator(data, key):
        raise Invalid(_('8|The latest date must include a day'))

def custom_earliest_year_validator(key, data, errors, context):
    if _custom_date_field_validator(data, key):
        raise Invalid(_('9|The earliest date must include a year'))

def custom_earliest_month_validator(key, data, errors, context):
    if _custom_date_field_validator(data, key):
        raise Invalid(_('9|The earliest date must include a month'))

def custom_earliest_day_validator(key, data, errors, context):
    if _custom_date_field_validator(data, key):
        raise Invalid(_('9|The earliest date must include a day'))

def custom_regularly_updated_validatior(value):
    if not value:
        raise Invalid(_('7|Select if this dataset is updated regularly'))
    return value

def custom_data_available_validator(value):
    if not value:
        raise Invalid(_('6|Select if this dataset is available online'))
    return value

def custom_required_author_email_validator(key, data, errors, context):
    data_available = data.get(('data_available',))
    value = data.get(key)
    if data_available == "no" and not value:
        raise Invalid(_('9|Enter contact email for people to request the dataset'))
    return value

def custom_required_author_name_validator(key, data, errors, context):
    data_available = data.get(('data_available',))
    value = data.get(key)
    if data_available == "no" and not value:
        raise Invalid(_('8|Enter contact name for people to request the dataset'))
    return value

def custom_topics_validator(key, data, errors, context):
    value = data.get(key)
    if not value:
        raise Invalid(_('6|Enter what topics best describe this dataset'))
    return value

def custom_date_range_start_converter(key, data, errors, context):
    start_date = ""
    regularly_updated = data.get(('regularly_updated',))
    if (regularly_updated == "no"):
        try:
            start_date = date(int(data.get(('date_range_earliest_year',))), int(data.get(('date_range_earliest_month',))), int(data.get(('date_range_earliest_day',)))).strftime("%Y-%m-%d %H:%M:%S")
        except:
                raise Invalid(_('6|Earliest date must be a real date'))
    elif (regularly_updated == "yes"):
        earliest_year = data.get(('regularly_updated_earliest_year',))
        earliest_month = data.get(('regularly_updated_earliest_month',))
        earliest_day = data.get(('regularly_updated_earliest_day',))
        if (earliest_year and earliest_month and earliest_day):
            try:
                start_date = date(int(earliest_year), int(earliest_month), int(earliest_day)).strftime("%Y-%m-%d %H:%M:%S")
            except:
                 raise Invalid(_('6|Earliest date must be a real date'))
        else:
            start_date = date(1900, 1, 1).strftime("%Y-%m-%d %H:%M:%S")
    data.update({('start_date',): start_date})

def custom_date_range_end_converter(key, data, errors, context):
    end_date = ""
    regularly_updated = data.get(('regularly_updated',))
    if (regularly_updated == "no"):
        try:
            end_date = date(int(data.get(('date_range_latest_year',))), int(data.get(('date_range_latest_month',))), int(data.get(('date_range_latest_day',)))).strftime("%Y-%m-%d %H:%M:%S")
        except:
            raise Invalid(_('5|Latest date must be a real date'))
    else:
        try:
            end_date = date.max.strftime("%Y-%m-%d %H:%M:%S")
        except:
            raise Invalid(_('5|Latest date must be a real date'))
    data.update({('end_date',): end_date})

def _create_tag_vocabulary(vocab_name, tags):
    user = toolkit.get_action('get_site_user')({'ignore_auth': True}, {})
    context = {'user': user['name']}
    try:
        data = {'id': vocab_name }
        toolkit.get_action('vocabulary_show')(context, data)
        vocab_list = toolkit.get_action('vocabulary_show')(context, data)
        vocab_tag_names = [o['name'] for o in vocab_list['tags']]
        for tag in tags:
            if tag not in vocab_tag_names:
                data = {'name': tag, 'vocabulary_id': vocab_list['id']}
                toolkit.get_action('tag_create')(context, data)
    except toolkit.ObjectNotFound:
        data = {'name': vocab_name }
        vocab = toolkit.get_action('vocabulary_create')(context, data)
        for tag in tags:
            data = {'name': tag, 'vocabulary_id': vocab['id']}
            toolkit.get_action('tag_create')(context, data)

def _get_tag_vocabulary_tags(vocab_name):
    try:
        tag_list = toolkit.get_action('tag_list')
        tags = tag_list(data_dict={'vocabulary_id': vocab_name})
        tags.sort(key = 'Other'.__eq__)
        return tags
    except toolkit.ObjectNotFound:
        return None

def create_topics():
    topics = (
        u'Air quality and the environment',
        u'Accidents and incidents',
        u'Assets and asset management',
        u'Car parks',
        u'Freight and logistics',
        u'Parking and rest areas',
        u'Public transport',
        u'Roadworks',
        u'Safety',
        u'Street works',
        u'Temporary measures',
        u'Tolls and toll stations',
        u'Traffic data',
        u'Traffic signs and regulations',
        u'Trip planning',
        u'Utilities',
        u'Fleets',
        u'Contraventions',
        u'Permits',
        u'Other'
    )
    _create_tag_vocabulary('nap_topics', topics)

def create_transport_modes():
    transport_modes = (
        u'Cars',
        u'Trucks',
        u'Bicycles',
        u'Electric vehicles',
        u'Multi-modal',
        u'Pedestrians',
        u'Buses',
        u'Demand-responsive',
        u'Motorcycles',
        u'Other'
    )
    _create_tag_vocabulary('nap_transport_modes', transport_modes)
    
def create_road_network():
    road_networks = (
        u'Motorways',
        u'Roads',
        u'Dual carriageways',
        u'Single carriageways',
        u'Gradients',
        u'Junctions',
        u'Bridges',
        u'Other'
    )
    _create_tag_vocabulary('nap_road_networks', road_networks)

def get_road_networks():
    create_road_network()
    return _get_tag_vocabulary_tags('nap_road_networks')

def get_topics():
    create_topics()
    return _get_tag_vocabulary_tags('nap_topics')


def get_transport_modes():
    create_transport_modes()
    return _get_tag_vocabulary_tags('nap_transport_modes')

def get_user_with_datasets(user):
    data_dict = {u'user_obj': user, u'include_datasets': True}
    return logic.get_action('user_show')({}, data_dict)

def get_user_with_plugin_extras(id):
    data_dict = {u'id': id, u'include_plugin_extras': True}
    return logic.get_action('user_show')({}, data_dict)

def get_all_users():
    users = logic.get_action('user_list')({}, {})
    return users

def sort_users_created(e):
    return e['created']

def sort_users_name(e):
    return e['name']

def get_unauthorised_users():
    users = get_all_users()
    unauthorised_users = [user for user in users if user['about'] == 'unauthorised']
    unauthorised_users.sort(key=sort_users_created)
    return unauthorised_users

def get_rejected_users():
    users = get_all_users()
    rejected_users = [user for user in users if user['about'] == 'rejected']
    rejected_users.sort(key=sort_users_created)
    for user in rejected_users:
        full_user = get_user_with_plugin_extras(user['id'])
        user['plugin_extras'] = full_user['plugin_extras']
    return rejected_users

def get_approved_users():
    users = get_all_users()
    approved_users = [user for user in users if user['about'] == '' and user['sysadmin'] == False]
    approved_users.sort(key=sort_users_name)
    for user in approved_users:
        full_user = get_user_with_plugin_extras(user['id'])
        user['plugin_extras'] = full_user['plugin_extras']
    return approved_users

def get_admin_users():
    users = get_all_users()
    admin_users = [user for user in users if user['name'] != 'admin' and user['name'] != 'default' and user['sysadmin'] == True]
    admin_users.sort(key=sort_users_name)
    return admin_users

def _get_item_from_list(item_list,key, key_value, item):
    for list_item in item_list:
        if list_item[key] == key_value:
            return list_item[item]
    return ''

def get_update_frequencies():
    update_frequencies = [
        {'name': 'Live', 'value': 'live'},
        {'name': 'Daily', 'value': 'daily'},
        {'name': 'Weekly', 'value': 'weekly'},
        {'name': '2 Weekly', 'value': '2weekly'},
        {'name': '4 Weekly', 'value': '4weekly'},
        {'name': 'Monthly', 'value': 'monthly'},
        {'name': 'Quarterly', 'value': 'quarterly'},
        {'name': '6 Monthly', 'value': '6monthly'},
        {'name': 'Yearly', 'value': 'yearly'}
    ]
    return update_frequencies

def get_update_frequency_name(value):
    update_frequencies = get_update_frequencies()
    return _get_item_from_list(update_frequencies,'value',value,'name')

def get_licences():
    licences = [
        {'type':'Free', 'name': 'Creative Commons Attribution', 'value': 'cc-by'},
        {'type':'Free', 'name': 'Creative Commons Attribution Share-Alike', 'value': 'cc-by-sa'},
        {'type':'Free', 'name': 'Creative Commons CCZero', 'value': 'cc-zero'},
        {'type':'Free', 'name': 'Creative Commons Non-Commercial (Any)', 'value': 'cc-nc'},
        {'type':'Free', 'name': 'GNU Free Documentation Licence', 'value': 'gfdl'},
        {'type':'Free', 'name': 'Licence not specified', 'value': 'notspecified'},
        {'type':'Free', 'name': 'Open Data Commons Attribution Licence', 'value': 'odc-by'},
        {'type':'Free', 'name': 'Open Data Commons Open Database Licence (ODbL)', 'value': 'odc-odbl'},
        {'type':'Free', 'name': 'Open Data Commons Public Domain Dedication and Licence (PDDL)', 'value': 'odc-pddl'},
        {'type':'Free', 'name': 'Other (Attribution)', 'value': 'other-at'},
        {'type':'Free', 'name': 'Other (Non-Commercial)', 'value': 'other-nc'},
        {'type':'Free', 'name': 'Other (Open)', 'value': 'other-open'},
        {'type':'Free', 'name': 'Other (Public Domain)', 'value': 'other-pd'},
        {'type':'Free', 'name': 'UK Open Government Licence (OGL)', 'value': 'uk-ogl'},
        {'type':'Commercial', 'name': 'Commercial Licence', 'value': 'commercial'},
        {'type':'Closed', 'name': 'Other (Not open)', 'value': 'other-closed'},
    ]
    return licences

def get_licence_name(value):
    licenses = get_licences()
    return _get_item_from_list(licenses,'value',value,'name')

def get_licence_type(value):
    licenses = get_licences()
    return _get_item_from_list(licenses,'value',value,'type')

def get_time_period(package):
    if package['regularly_updated'] == 'yes':
        if package['regularly_updated_earliest_year'] == '':
            time_period = ''
        else:
            time_period = f"{package['regularly_updated_earliest_day']}/{package['regularly_updated_earliest_month']}/{package['regularly_updated_earliest_year']}- Present"
    else:
        time_period =f"{package['date_range_earliest_day']}/{package['date_range_earliest_month']}/{package['date_range_earliest_year']} - {package['date_range_latest_day']}/{package['date_range_latest_month']}/{package['date_range_latest_year']}" 
    return time_period

def get_date_formatted(date_type, date_format):
    return datetime.strptime(date_type[:10],"%Y-%m-%d").strftime(date_format)

def get_date_time_formatted(date_type, date_format):
    try:
        return datetime.strptime(date_type,"%Y-%m-%dT%H:%M:%S.%f").strftime(date_format)
    except:
        try:
            return datetime.strptime(date_type,"%Y-%m-%d %H:%M:%S").strftime(date_format)
        except:
            return ''
    return ''
    
def get_facets(list, start_date, end_date):
    if not list and start_date == '' and end_date == '':
        return list
    new_list = {}
    added = False
    for key, value in list.items() or []:
        if key == 'update_frequency':
            added = True
            if start_date != '':
                new_list['time-period-start'] = [get_date_formatted(start_date,'%d/%m/%Y')]
            if end_date != '':
                new_list['time-period-end'] = [get_date_formatted(end_date,'%d/%m/%Y')]
        new_list[key] = value
    if not added:
        if start_date != '':
            new_list['time-period-start'] = [get_date_formatted(start_date,'%d/%m/%Y')]
        if end_date != '':
            new_list['time-period-end'] = [get_date_formatted(end_date,'%d/%m/%Y')]
    return new_list

class NapThemePlugin(plugins.SingletonPlugin, toolkit.DefaultDatasetForm):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IDatasetForm)

    # IConfigurer
    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'fanstatic')
        toolkit.add_resource('fanstatic', 'nap_theme')

    # ITemplateHelpers 
    def get_helpers(self):
        return {
            'nap_theme_get_extra': get_extra, 
            'nap_theme_get_orgs': get_orgs, 
            'nap_theme_get_tags': get_tags,
            'nap_theme_get_tag_names': get_tag_names,
            'nap_theme_get_sorted_error_summary': get_sorted_error_summary,
            'nap_theme_get_form_data' : get_form_data,
            'nap_theme_get_package_display_name' : get_package_display_name,
            'nap_theme_get_topics': get_topics,
            'nap_theme_get_transport_modes': get_transport_modes,
            'nap_theme_get_road_networks': get_road_networks,
            'nap_theme_get_user_with_datasets': get_user_with_datasets,
            'nap_theme_get_update_frequencies' : get_update_frequencies,
            'nap_theme_get_update_frequency_name' : get_update_frequency_name,
            'nap_theme_get_licences' : get_licences,
            'nap_theme_get_licence_name' : get_licence_name,
            'nap_theme_get_licence_type' : get_licence_type,
            'nap_theme_get_time_period' : get_time_period,
            'nap_theme_get_date_formatted' : get_date_formatted,
            'nap_theme_get_date_time_formatted' : get_date_time_formatted,
            'nap_theme_get_facets' : get_facets,
            'nap_theme_get_all_users': get_all_users,
            'nap_theme_send_application_submitted_email' : send_application_submitted_email,
            'nap_theme_get_reset_password_feature_flag' : get_reset_password_feature_flag,
            'nap_theme_get_create_account_feature_flag' : get_create_account_flag
            }

    # IBlueprint
    def get_blueprint(self):
        u'''Return a Flask Blueprint object to be registered by the app.'''
        # Create Blueprint for plugin
        blueprint = Blueprint(self.name, self.__module__)
        blueprint.template_folder = u'templates'
        # Add plugin url rules to Blueprint object
        blueprint.add_url_rule(u'/cookies', u'cookies', cookies)
        blueprint.add_url_rule(u'/user/register/submitted', u'application_submitted', application_submitted)
        blueprint.add_url_rule(u'/user/admin/applications', u'admin_applications', admin_applications)
        blueprint.add_url_rule(u'/user/admin/approved', u'admin_approved', admin_approved)
        blueprint.add_url_rule(u'/user/admin/admins', u'admin_admins', admin_admins)
        blueprint.add_url_rule(u'/user/admin/rejected', u'admin_rejected', admin_rejected)
        blueprint.add_url_rule(u'/user/admin/application/<id>/approve', u'admin_approve_application', admin_approve_application)
        blueprint.add_url_rule(u'/user/admin/application/approved', u'admin_application_approved', admin_application_approved, methods=['POST'])
        blueprint.add_url_rule(u'/user/admin/application/<id>/reject', u'admin_reject_application', admin_reject_application)
        blueprint.add_url_rule(u'/user/admin/application/rejected', u'admin_application_rejected', admin_application_rejected, methods=['POST'])
        blueprint.add_url_rule(u'/user/user/deleted', u'admin_delete_user', admin_delete_user, methods=['POST'])
        _govuk_reset_view = govUkPasswordResetView.as_view(str(u'request_reset'))
        blueprint.add_url_rule(u'/user/reset/',view_func=_govuk_reset_view)
        return blueprint

    def _create_search_param_dict(self, filter_query):
        from collections import defaultdict
        # fix issue with spaces in params such as tags we need to differentiate spaces between search terms and spaces
        filter_query = filter_query.replace('" ','"|||')
        # fix issue with : in params
        filter_query = filter_query.replace(':"','~~~"')
        filter_params = filter_query.split('|||')
        filter_dict = list(s.split('~~~') for s in filter_params)
        new_dict = defaultdict(list)
        for (key, value) in filter_dict:
            new_dict[key].append(value)
        return new_dict

    # IPackageController
    def before_search(self, search_params):
        def make_filters_or(filter_dict):
            filter_string = ""
            for (key, value) in filter_dict.items():
                string = f'{key}:({" OR ".join(value)})'
                filter_string = filter_string + " " + string
            return filter_string
    
        if (search_params.get('fq', None) and not '+owner_org' in search_params['fq'] and not '+creator_user_id' in search_params['fq']):
            fq = make_filters_or(self._create_search_param_dict(search_params['fq']))
            search_params["fq"] = fq
        
        extras = search_params.get('extras')
        start_date = extras.get('ext_startdate')
        end_date = extras.get('ext_enddate')
        if not start_date or not end_date:
            return search_params
        
        start_date = datetime.strptime(start_date, '%Y-%m-%d').strftime("%Y-%m-%dT%H:%M:%SZ")
        end_date = datetime.strptime(end_date, '%Y-%m-%d').strftime("%Y-%m-%dT%H:%M:%SZ")

        fq = search_params["fq"]
        fq = '{fq} (start_date:[* TO {end_date}] AND end_date:[{start_date} TO *])'.format(
        fq=fq, start_date=start_date, end_date=end_date)
        search_params["fq"] = fq
        return search_params

    # Schema Changes
    def is_fallback(self):
       # Return True to register this plugin as the default handler for
       # package types not handled by any other IDatasetForm plugin.
       return True

    def package_types(self):
       # This plugin doesn't handle any special package types, it just
       # registers itself as the default (above).
       return []

    def create_package_schema(self):
       schema = super(NapThemePlugin, self).create_package_schema()
       schema = self._modify_package_schema(schema)
       return schema

    def update_package_schema(self):
       schema = super(NapThemePlugin, self).update_package_schema()
       schema = self._modify_package_schema(schema)
       return schema

    def _modify_package_schema(self, schema):
        schema.update({
            'url':[custom_url_validator,
                toolkit.get_converter('unicode_safe')],
            'title':[custom_description_validator,
                toolkit.get_converter('unicode_safe')],
            'author_email':[toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('unicode_safe'),
                custom_author_email_validator,
                custom_required_author_email_validator],
            'author':[toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('unicode_safe'),
                custom_required_author_name_validator],
            'name':[toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('unicode_safe')],
            'location':[custom_location_validator,
                toolkit.get_converter('convert_to_extras')],
            'data_formats':[toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_to_extras')],
            'update_frequency':[custom_update_frequency_validator,
                toolkit.get_converter('convert_to_extras')],
            'regularly_updated':[custom_regularly_updated_validatior,
                toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_to_extras')],
            'date_range_earliest_day': [custom_earliest_day_validator,
                toolkit.get_converter('convert_to_extras')],
            'date_range_earliest_month': [custom_earliest_month_validator,
                toolkit.get_converter('convert_to_extras')],
            'date_range_earliest_year': [custom_earliest_year_validator,
                toolkit.get_converter('convert_to_extras')],
            'date_range_latest_day': [custom_latest_day_validator,
                toolkit.get_converter('convert_to_extras')],
            'date_range_latest_month': [custom_latest_month_validator,
                toolkit.get_converter('convert_to_extras')],
            'date_range_latest_year': [custom_latest_year_validator,
                toolkit.get_converter('convert_to_extras')],
            'date_range_earliest': [custom_date_range_earliest_validator],
            'date_range_latest': [custom_date_range_latest_validator],
            'regularly_updated_earliest_day':[toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_to_extras')],
            'regularly_updated_earliest_month':[toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_to_extras')],
            'regularly_updated_earliest_year':[toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_to_extras')],
            'data_available':[custom_data_available_validator,
                toolkit.get_converter('convert_to_extras')],
            'topics':[custom_topics_validator,
                    toolkit.get_validator('ignore_missing'),
                    toolkit.get_converter('convert_to_tags')('nap_topics')],
            'transport_modes':[toolkit.get_validator('ignore_missing'),
                    toolkit.get_converter('convert_to_tags')('nap_transport_modes')],
            'road_networks':[toolkit.get_validator('ignore_missing'),
                    toolkit.get_converter('convert_to_tags')('nap_road_networks')],
            'start_date':[custom_date_range_start_converter,
                    toolkit.get_converter('convert_to_extras')],
            'end_date':[custom_date_range_end_converter,
                    toolkit.get_converter('convert_to_extras')]
        })
        return schema

    def show_package_schema(self):
        schema = super(NapThemePlugin, self).show_package_schema()

        schema.update({
            'url':[toolkit.get_converter('unicode_safe'),
                custom_url_validator],
            'title':[toolkit.get_converter('unicode_safe'),
                custom_description_validator],
            'author_email':[toolkit.get_converter('unicode_safe'),
                toolkit.get_validator('ignore_missing'),
                custom_author_email_validator,
                custom_required_author_email_validator],
            'author': [toolkit.get_converter('unicode_safe'),
                toolkit.get_validator('ignore_missing'),
                custom_required_author_name_validator],
            'name':[toolkit.get_converter('unicode_safe'),
                    toolkit.get_validator('ignore_missing')],
            'location':[toolkit.get_converter('convert_from_extras'),
                custom_location_validator],
            'data_formats':[toolkit.get_converter('unicode_safe'),
                    toolkit.get_validator('convert_from_extras')],
            'update_frequency':[toolkit.get_converter('unicode_safe'),
                    toolkit.get_validator('convert_from_extras')],
            'regularly_updated':[toolkit.get_converter('unicode_safe'),
                    toolkit.get_validator('ignore_missing'),
                    toolkit.get_converter('convert_from_extras')],
            'date_range_earliest_day': [toolkit.get_converter('unicode_safe'),
                    custom_earliest_day_validator,
                    toolkit.get_converter('convert_from_extras')],
            'date_range_earliest_month': [toolkit.get_converter('unicode_safe'),
                    custom_earliest_month_validator,
                    toolkit.get_converter('convert_from_extras')],
            'date_range_earliest_year': [toolkit.get_converter('unicode_safe'),
                    custom_earliest_year_validator,
                    toolkit.get_converter('convert_from_extras')],
            'date_range_latest_day': [toolkit.get_converter('unicode_safe'), 
                    custom_latest_day_validator,
                    toolkit.get_converter('convert_from_extras')],
            'date_range_latest_month': [toolkit.get_converter('unicode_safe'), 
                    custom_latest_month_validator,
                    toolkit.get_converter('convert_from_extras')],
            'date_range_latest_year': [toolkit.get_converter('unicode_safe'), 
                    custom_latest_year_validator,
                    toolkit.get_converter('convert_from_extras')],
            'regularly_updated_earliest_day':[toolkit.get_converter('unicode_safe'),
                toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_from_extras')],
            'regularly_updated_earliest_month':[toolkit.get_converter('unicode_safe'),
                toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_from_extras')],
            'regularly_updated_earliest_year':[toolkit.get_converter('unicode_safe'),
                toolkit.get_validator('ignore_missing'),
                toolkit.get_converter('convert_from_extras')],
            'data_available':[custom_data_available_validator,
                    toolkit.get_converter('unicode_safe'),
                    toolkit.get_converter('convert_from_extras')],
            'topics':[custom_topics_validator,
                    toolkit.get_converter('convert_from_tags')('nap_topics'),
                    toolkit.get_validator('ignore_missing')],
            'transport_modes':[ toolkit.get_converter('convert_from_tags')('nap_transport_modes'),
                    toolkit.get_validator('ignore_missing')],
            'road_networks':[toolkit.get_converter('convert_from_tags')('nap_road_networks'),
                    toolkit.get_validator('ignore_missing')],
            'start_date':[toolkit.get_converter('convert_from_extras')],
            'end_date':[toolkit.get_converter('convert_from_extras')]
        })
        return schema  

    def user_new_form_schema(self):
        schema = super(NapThemePlugin, self).user_new_form_schema()
        schema.update({
            'image_url':[custom_user_organisation_validator,
                toolkit.get_converter('unicode_safe')],
            'fullname':[custom_user_fullname_validator,
                toolkit.get_converter('unicode_safe')],
        })
        return schema

    # IValidators
    def get_validators(self):
        return {
            u'owner_org_validator': custom_owner_org_validator,
            u'url_validator': custom_url_validator,
            u'title_validator': custom_title_validator,
            u'location_validator': custom_location_validator
        }

class govUkPasswordResetView(RequestResetView):
    def _create_reset_key(self, user):
        user.reset_key = text_type(self._make_key())
        model.repo.commit_and_remove()

    def _make_key(self):
        return codecs.encode(os.urandom(16), 'hex')

    def _verify_reset_link(self, user, key):
        if not key:
            return False
        if not user.reset_key or len(user.reset_key) < 5:
            return False
        return key.strip() == user.reset_key
    
    def _get_reset_link(self, user):
        return h.url_for(controller='user',
            action='perform_reset',
            id=user.id,
            key=user.reset_key,
            qualified=True)

    def send_reset_link(self, user):
        self._create_reset_key(user)

        # GOV NOTIFY Code here
        reset_link = self._get_reset_link(user)
        name = user.fullname if user.fullname else user.name
        reset_password_link_email(user.email, name, reset_link)

    def post(self):
        email = request.form.get(u'user')
        if email in (None, u''):
            h.flash_error(_(u'Please enter your email'))
            return h.redirect_to(u'/user/reset')

        context = {u'model': model, u'user': toolkit.g.user, u'ignore_auth': True}
        user_list = logic.get_action(u'user_list')(context, {
                u'email': email
            })
        if(user_list):
            user_objs = []
            for user_dict in user_list:
                    # This is ugly, but we need the user object for the mailer,
                    # and user_list does not return them
                    logic.get_action(u'user_show')(
                        context, {u'id': user_dict[u'id']})
                    user_objs.append(context[u'user_obj'])

            for user_obj in user_objs:
                self.send_reset_link(user_obj)

        h.flash_success(
            _(u'A reset link has been emailed to you '
            '(unless the account specified does not exist)'))
        return h.redirect_to(u'/user/reset')
    
    def get(self):
        return super(govUkPasswordResetView, self).get()
