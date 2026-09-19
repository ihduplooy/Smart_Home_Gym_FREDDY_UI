"""Thin adapter routes for the GYM tab's rotary encoder -> Weight field link
(core/hardware/weight_encoder.py). Independent of the Train session
lifecycle and ODrive connection state -- the encoder's singleton runs
regardless of whether a device is connected or scanned.
"""

import logging

from flask import jsonify, request

from core.hardware.weight_encoder import weight_encoder

log = logging.getLogger(__name__)


def register(app) -> None:
    @app.route("/api/gym/weight", methods=["GET"])
    def gym_weight_get():
        return jsonify({"weight_kg": weight_encoder.get_weight_kg()})

    @app.route("/api/gym/weight", methods=["POST"])
    def gym_weight_set():
        body = request.get_json(silent=True) or {}
        try:
            weight_kg = float(body.get("weight_kg"))
        except (TypeError, ValueError):
            return jsonify({"error": "weight_kg must be a number"}), 400
        weight_encoder.set_weight_kg(weight_kg)
        return jsonify({"weight_kg": weight_encoder.get_weight_kg()})
