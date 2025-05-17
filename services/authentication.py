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



from functools import wraps
from flask import request, jsonify
from models import APIKey

def authenticate(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        api_key_value = request.headers.get('X-API-Key')
        api_key = APIKey.query.filter_by(key=api_key_value, revoked=False).first()
        
        if not api_key or not api_key.is_valid():
            return jsonify({"message": "Unauthorized"}), 401
            
        # Update last used timestamp
        from datetime import datetime
        api_key.last_used_at = datetime.utcnow()
        from models import db
        db.session.commit()
        
        return func(*args, **kwargs)
    return wrapper
