#!/usr/bin/env python3
# webhook2kafka
# Copyright(C) 2019 Christoph Görn
#
# This program is free software: you can redistribute it and / or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


"""This will send all the webhook payloads to a Kafka topic."""

import os
import sys
import ssl
import logging
import json
from http import HTTPStatus


import faust


from thoth.common import init_logging
from thoth.messaging import PackageRelease


from aiohttp import web


__version__ = "0.1.0-dev"

_DEBUG = os.getenv("DEBUG", False)


init_logging()
_LOGGER = logging.getLogger("webhook2kafka")
_LOGGER.setLevel(logging.DEBUG if _DEBUG else logging.INFO)

_KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
_KAFKA_SSL_CAFILE = os.getenv("KAFKA_SSL_CAFILE", "secrets/data-hub-kafka-ca.crt")
_KAFKA_TOPIC_RETENTION_TIME_SECONDS = 60 * 60 * 24 * 45


ssl_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile="secrets/data-hub-kafka-ca.crt")
faust_app = faust.App(
    "package_releases_webhook2kafka",
    broker=_KAFKA_BOOTSTRAP_SERVERS,
    value_serializer="json",
    ssl_context=ssl_context,
    web_enabled=False,
)
package_releases_topic = faust_app.topic(
    "thoth_package_releases", value_type=PackageRelease, retention=_KAFKA_TOPIC_RETENTION_TIME_SECONDS
)


app = web.Application()
routes = web.RouteTableDef()


@routes.get("/")
async def hello(request):
    """Return just a default greeting."""
    return web.json_response({"text": "thanks for the GET method"})


@routes.post("/webhook")
async def forward_webhook_to_topic(request):
    """Entry point for a webhook."""
    payload = request.json

    try:
        await package_releases_topic.send(value=PackageRelease("index_url", "package_name", "package_version"))

    except Exception as e:
        _LOGGER.exception(e)

    return web.json_response({"status": "success"})


def _valide_configuration() -> bool:
    """Check if all the required prerequisites are fulfulled."""
    if os.path.isfile(_KAFKA_SSL_CAFILE):
        return True
    else:
        _LOGGER.error(f"Missing SSL CA File: {_KAFKA_SSL_CAFILE}")
        return False


if __name__ == "__main__":
    _LOGGER.info(f"Package Releases webhook2kafka v{__version__} started.")
    _LOGGER.debug("DEBUG mode is enabled!")

    if not _valide_configuration():
        _LOGGER.error("not all prerequisites are fulfilled!")
        exit(-1)

    _LOGGER.info(f"running HTTP application now...")

    app.add_routes(routes)

    web.run_app(app)
