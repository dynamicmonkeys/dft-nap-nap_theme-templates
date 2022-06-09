#!/bin/bash

docker exec ckan ckan -c /srv/app/production.ini search-index rebuild