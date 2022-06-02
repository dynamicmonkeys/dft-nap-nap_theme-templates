FROM radicalgeektechnology/ckan:2.9.2

COPY fanstatic /usr/lib/ckan/default/src/ckanext-nap_theme/ckanext/nap_theme/fanstatic/
COPY templates  /usr/lib/ckan/default/src/ckanext-nap_theme/ckanext/nap_theme/templates/
COPY webassets /tmp/webassets/

#WORKDIR /usr/lib/ckan/default/src/ckanext-nap_theme
#RUN /bin/bash -c 'pip3 install -r requirements.txt; python3 setup.py develop; supervisorctl reload'
#RUN /bin/bash -c 'service nginx stop; rm -r /tmp/nginx_cache/; service nginx start'
