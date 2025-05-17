from flask import Flask, request, jsonify
from flask_login import LoginManager
from flask_migrate import Migrate
from models import db, User, APIKey
import os

def create_app():
    app = Flask(__name__, template_folder='templates')
    
    # Configure SQLAlchemy and other settings
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'web_auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Create database tables
    with app.app_context():
        db.create_all()

    # Import and register web interface blueprints
    from routes.web.auth import web_auth_bp
    app.register_blueprint(web_auth_bp)

    # Add a test API endpoint to verify API key authentication
    @app.route('/api/test', methods=['GET'])
    def test_api():
        api_key_value = request.headers.get('X-API-Key')
        api_key = APIKey.query.filter_by(key=api_key_value, revoked=False).first()
        
        if not api_key or not api_key.is_valid():
            return jsonify({"message": "Unauthorized"}), 401
            
        # Update last used timestamp
        from datetime import datetime
        api_key.last_used_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "message": "API key is valid",
            "user_email": api_key.user.email,
            "key_name": api_key.name,
            "created_at": api_key.created_at.isoformat(),
            "last_used_at": api_key.last_used_at.isoformat()
        }), 200

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
