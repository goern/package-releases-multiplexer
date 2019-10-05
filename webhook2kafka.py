#!/usr/bin/env python3
# webhook2kafka
# Copyright(C) 2018 Christoph Görn
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


"""This will send all the GitHub webhooks to a Kafka topic."""

import os
import hmac
import logging
import json
import sys
from http import HTTPStatus


import daiquiri
import kafka
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic

from flask import Flask, Response, jsonify, make_response, request, current_app
from prometheus_flask_exporter import PrometheusMetrics


__version__ = "0.2.0-dev"


_DEBUG = os.getenv("DEBUG", False)


daiquiri.setup()
_LOGGER = daiquiri.getLogger("webhook2kafka")
_LOGGER.setLevel(logging.DEBUG if _DEBUG else logging.INFO)

KAFAK_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_SSL_CAFILE = os.getenv("KAFKA_SSL_CAFILE", "datahub-kafka.crt")

THOTH_PACKAGE_RELEASES_TOPIC_NAME = "thoth_package_releases"


app = Flask(__name__)
metrics = PrometheusMetrics(app)
metrics.info("thoth_package_releases_webhook2kafka_info", "Thoth's Package Releases webhook2kafka", version=__version__)


@app.after_request
def add_app_version(response):
    response.headers["X-Thoth-Package-Releases"] = __version__
    return response


@app.route("/")
def root():
    return f"This service is for Bots only, anyway, here is a tiny glimpse into what I am: v{__version__}"


@app.route("/healthz")
@metrics.do_not_track()
def healthz():
    status_code = HTTPStatus.OK
    health = {"version": __version__}

    return make_response(jsonify(health), status_code)


@app.route("/webhook", methods=["POST"])
def send_webhook_to_topic():
    """Entry point for github webhook."""
    resp = Response()
    payload = None
    status_code = HTTPStatus.OK
    payload = request.json

    if payload is None:
        _LOGGER.error("GitHub webhook payload was empty")
        return resp, HTTPStatus.INTERNAL_SERVER_ERROR

    _publish(THOTH_PACKAGE_RELEASES_TOPIC_NAME, payload)

    return resp, status_code


def _publish(topic: str, payload: dict) -> str:
    """Publish the given dict to topic."""
    producer = None
    status_code = HTTPStatus.OK

    if producer is None:
        _LOGGER.debug("KafkaProducer was not connected, trying to reconnect...")
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFAK_BOOTSTRAP_SERVERS,
                acks=0,  # Wait for leader to write the record to its local log only.
                compression_type="gzip",
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                security_protocol="SSL",
                ssl_cafile=KAFKA_SSL_CAFILE,
            )
        except kafka.errors.NoBrokersAvailable as excptn:
            _LOGGER.debug("while trying to reconnect KafkaProducer: we failed...")
            _LOGGER.error(excptn)
            return HTTPStatus.INTERNAL_SERVER_ERROR

    try:
        future = producer.send(topic, payload)
        result = future.get(timeout=6)
        _LOGGER.debug(result)
    except AttributeError as excptn:
        _LOGGER.debug(excptn)
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    except (kafka.errors.NotLeaderForPartitionError, kafka.errors.KafkaTimeoutError) as excptn:
        _LOGGER.error(excptn)
        producer.close()
        producer = None

        status_code = HTTPStatus.INTERNAL_SERVER_ERROR

    return status_code


if __name__ == "__main__":
    _LOGGER.info(f"Thoth's Package Releases webhook2kafka v{__version__} started.")
    _LOGGER.debug("DEBUG mode is enabled!")

    app.config["GITHUB_WEBHOOK_SECRET"] = os.environ.get("GITHUB_WEBHOOK_SECRET")

    if os.environ.get("KAFKA_CREATE_TOPICS"):
        topic_list = []
        topic_list.append(NewTopic(name=THOTH_PACKAGE_RELEASES_TOPIC_NAME, num_partitions=1, replication_factor=1))

        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFAK_BOOTSTRAP_SERVERS,
            client_id="package_releases_multiplexer",
            security_protocol="SSL",
            ssl_cafile=KAFKA_SSL_CAFILE,
        )
        admin_client.create_topics(new_topics=topic_list, validate_only=False)

    _LOGGER.info(f"running Flask application now...")
    app.run(host="0.0.0.0", port=8080, debug=_DEBUG)
