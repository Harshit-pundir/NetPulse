from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from ..models import User
bp = Blueprint('auth', __name__)
@bp.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        user=User.query.filter_by(username=request.form.get('username','').strip()).first()
        if user and check_password_hash(user.password_hash, request.form.get('password','')):
            login_user(user); return redirect(url_for('dashboard.index'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')
@bp.post('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('auth.login'))
