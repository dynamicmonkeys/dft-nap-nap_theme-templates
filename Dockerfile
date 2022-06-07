    ###################
    ### Extensions ####
    ###################
    FROM keitaro/ckan:2.9.2 as extbuild

    # Switch to the root user
    USER root
    # Change the repo to be the NAP Theme REPO!!!
    # We need to install the requirments speciaclly for Gov Notify which is specifed in the requirements.txt
    #RUN pip wheel --wheel-dir=/wheels -r https://github.com/departmentfortransport/ckanext-dftnap/blob/master/beta/ckanext/ckanext-nap_theme/requirements.txt
    #RUN curl -o /srv/requirements.txt https://raw.githubusercontent.com/andy-eagle/ckanext-nap_theme/main/requirements.txt?token=GHSAT0AAAAAABQY2WPBJPIIAK3BNWL7PFRWYQFH56Q
    RUN mkdir tmp
    COPY requirements.txt /srv/requirements.txt
    COPY src /srv
    RUN pip wheel --wheel-dir=/wheels /srv
    RUN pip wheel --wheel-dir=/wheels -r /srv/requirements.txt


    ############
    ### MAIN ###
    ############
    FROM keitaro/ckan:2.9.2

    # Add the custom extensions to the plugins list
    ENV CKAN__PLUGINS envvars image_view text_view recline_view datastore datapusher nap_theme

    # Switch to the root user
    USER root
    
    COPY --from=extbuild /wheels /srv/app/ext_wheels

    # Install and enable the custom extensions
    #RUN pip install ckanext-nap_theme && \
    RUN pip install --no-index --find-links=/srv/app/ext_wheels ckanext-nap_theme && \
        pip install --no-index --find-links=/srv/app/ext_wheels notifications-python-client && \
        ckan config-tool ${APP_DIR}/production.ini "ckan.plugins = ${CKAN__PLUGINS}" && \
        ckan config-tool ${APP_DIR}/production.ini "ckanext.nap_theme.gov_notify_key = ckanteam-434371f5-3850-4f7b-92d0-b64651438044-fcbf118c-be66-4234-9e53-3bc092c8368a" && \
        chown -R ckan:ckan /srv/app
    
    # Switch to the ckan user
    USER ckan
