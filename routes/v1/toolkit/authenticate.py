# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.



from flask import Blueprint, request, jsonify, current_app
# from app_utils import * # Assuming queue_task_wrapper is no longer needed
from functools import wraps
from models import APIKey # APIKey model might still be needed if other auth logic exists, or can be removed if app.queue_task handles all
import os

v1_toolkit_auth_bp = Blueprint('v1_toolkit_auth', __name__)


@v1_toolkit_auth_bp.route('/v1/toolkit/authenticate', methods=['GET'])
@current_app.queue_task(bypass_queue=True) # Use the decorator from the app instance
def authenticate_endpoint(**kwargs):
    # The API key check is now handled by the @current_app.queue_task decorator
    # This endpoint can now assume authentication was successful if it's reached.
    # The decorator in app.py will return 401 if auth fails.
    # If the key is valid, the decorator in app.py updates last_used_at.
    # This function will only be called if the API key is valid.
    return "Authorized", "/v1/toolkit/authenticate", 200
