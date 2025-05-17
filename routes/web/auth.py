from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from models import db, User, APIKey
from .forms import LoginForm, RegisterForm, APIKeyForm

web_auth_bp = Blueprint('web_auth', __name__, template_folder='../../templates')

@web_auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('web_auth.dashboard'))
    return redirect(url_for('web_auth.login'))

@web_auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('web_auth.dashboard'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash('Email already registered', 'error')
            return redirect(url_for('web_auth.register'))
        
        new_user = User(
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('web_auth.login'))
    
    return render_template('auth/register.html', form=form)

@web_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('web_auth.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            return redirect(url_for('web_auth.dashboard'))
        flash('Invalid email or password', 'error')
    
    return render_template('auth/login.html', form=form)

@web_auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('web_auth.login'))

@web_auth_bp.route('/dashboard')
@login_required
def dashboard():
    api_keys = APIKey.query.filter_by(user_id=current_user.id).all()
    form = APIKeyForm()
    return render_template('auth/dashboard.html', api_keys=api_keys, form=form)

@web_auth_bp.route('/generate-api-key', methods=['POST'])
@login_required
def generate_api_key():
    form = APIKeyForm()
    if form.validate_on_submit():
        api_key = APIKey(
            key=secrets.token_urlsafe(32),
            name=form.name.data,
            user_id=current_user.id
        )
        db.session.add(api_key)
        db.session.commit()
        flash('API key generated successfully', 'success')
    return redirect(url_for('web_auth.dashboard'))

@web_auth_bp.route('/revoke-api-key/<int:key_id>', methods=['POST'])
@login_required
def revoke_api_key(key_id):
    api_key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first_or_404()
    api_key.revoked = True
    db.session.commit()
    flash('API key revoked successfully', 'success')
    return redirect(url_for('web_auth.dashboard'))
