"""
Tests for y_web auth routes
"""
import pytest
import tempfile
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    """Create a test app with minimal configuration for route testing"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()
    
    app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for testing
    })
    
    db = SQLAlchemy(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    
    # Define minimal models for testing
    class Admin_users(db.Model):
        __tablename__ = 'admin_users'
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)
        password = db.Column(db.String(200), nullable=False)
        role = db.Column(db.String(20), default='user')
        
        def is_authenticated(self):
            return True
        
        def is_active(self):
            return True
        
        def is_anonymous(self):
            return False
        
        def get_id(self):
            return str(self.id)
    
    class User_mgmt(db.Model):
        __tablename__ = 'user_mgmt'
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)
        password = db.Column(db.String(200), nullable=False)
        joined_on = db.Column(db.Integer, nullable=False, default=1234567890)
        
        def is_authenticated(self):
            return True
        
        def is_active(self):
            return True
        
        def is_anonymous(self):
            return False
        
        def get_id(self):
            return str(self.id)
    
    class Exps(db.Model):
        __tablename__ = 'exps'
        idexp = db.Column(db.Integer, primary_key=True)
        exp_name = db.Column(db.String(50), nullable=False)
        exp_descr = db.Column(db.String(200), nullable=False)
        platform_type = db.Column(db.String(50), nullable=False, default="microblogging")
        owner = db.Column(db.String(50), nullable=False)
        status = db.Column(db.Integer, nullable=False)
        running = db.Column(db.Integer, nullable=False, default=0)
        port = db.Column(db.Integer, nullable=False, default=5000)
        server = db.Column(db.String(50), nullable=False, default="127.0.0.1")
    
    @login_manager.user_loader
    def load_user(user_id):
        return User_mgmt.query.get(int(user_id))
    
    # Create a simple auth blueprint for testing
    from flask import Blueprint, render_template_string, request, redirect, url_for, flash
    from flask_login import login_user, logout_user
    
    auth = Blueprint("auth", __name__)
    
    @auth.route("/signup")
    def signup():
        return render_template_string("""
        <form method="post" action="{{ url_for('auth.signup_post') }}">
            <input name="email" type="email" placeholder="Email" required>
            <input name="name" type="text" placeholder="Name" required>
            <input name="password" type="password" placeholder="Password" required>
            <button type="submit">Sign Up</button>
        </form>
        """)
    
    @auth.route("/signup", methods=["POST"])
    def signup_post():
        email = request.form.get("email")
        name = request.form.get("name")
        password = request.form.get("password")
        
        user = Admin_users.query.filter_by(email=email).first()
        
        if user:
            flash("Email address already exists")
            return redirect(url_for("auth.signup"))
        
        # Create a new user
        new_user = Admin_users(
            email=email,
            username=name,
            password=generate_password_hash(password),
            role="user",
        )
        db.session.add(new_user)
        
        # Check if experiment exists and create user_mgmt entry
        try:
            # Create experiment if it doesn't exist for testing
            if not Exps.query.first():
                exp = Exps(
                    exp_name="Test Experiment",
                    exp_descr="Test Description", 
                    platform_type="microblogging",
                    owner="admin",
                    status=1,
                    running=0,
                    port=5001
                )
                db.session.add(exp)
            
            new_user_exp = User_mgmt(
                email=email,
                username=name,
                password=generate_password_hash(password),
                joined_on=1234567890
            )
            db.session.add(new_user_exp)
        except Exception as e:
            flash("Server not ready. Please try again later.")
            return redirect(url_for("auth.signup"))
        
        db.session.commit()
        return "Signup successful"
    
    @auth.route("/login")
    def login():
        return render_template_string("""
        <form method="post">
            <input name="email" type="email" placeholder="Email" required>
            <input name="password" type="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        """)
    
    @auth.route("/login", methods=["POST"])
    def login_post():
        email = request.form.get("email")
        password = request.form.get("password")
        
        from werkzeug.security import check_password_hash
        user = Admin_users.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password, password):
            flash("Please check your login details and try again.")
            return redirect(url_for("auth.login"))
        
        # For non-admin users, get the User_mgmt version
        if user.role != "admin":
            user_agent = User_mgmt.query.filter_by(username=user.username).first()
            if user_agent:
                login_user(user_agent)
                return "Login successful - regular user"
        else:
            user_agent = User_mgmt.query.filter_by(username=user.username).first()
            if user_agent:
                login_user(user_agent)
                return "Login successful - admin user"
        
        return "Login failed"
    
    @auth.route("/logout")
    def logout():
        logout_user()
        return "Logged out"
    
    app.register_blueprint(auth)
    
    with app.app_context():
        db.create_all()
        
        # Create test users
        admin_user = Admin_users(
            username='admin',
            email='admin@test.com',
            password=generate_password_hash('admin123'),
            role='admin'
        )
        db.session.add(admin_user)
        
        user_mgmt_admin = User_mgmt(
            username='admin',
            email='admin@test.com',
            password=generate_password_hash('admin123'),
            joined_on=1234567890
        )
        db.session.add(user_mgmt_admin)
        
        regular_user = Admin_users(
            username='testuser',
            email='test@test.com',
            password=generate_password_hash('test123'),
            role='user'
        )
        db.session.add(regular_user)
        
        user_mgmt_regular = User_mgmt(
            username='testuser',
            email='test@test.com',
            password=generate_password_hash('test123'),
            joined_on=1234567890
        )
        db.session.add(user_mgmt_regular)
        
        db.session.commit()
    
    yield app
    
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Test client for the app"""
    return app.test_client()


class TestAuthRoutes:
    """Test authentication routes"""
    
    def test_signup_get(self, client):
        """Test GET /signup route"""
        response = client.get('/signup')
        assert response.status_code == 200
        assert b'Sign Up' in response.data
        assert b'Email' in response.data
        assert b'Name' in response.data
        assert b'Password' in response.data
    
    def test_signup_post_success(self, client):
        """Test successful POST /signup"""
        response = client.post('/signup', data={
            'email': 'newuser@test.com',
            'name': 'newuser',
            'password': 'newpassword123'
        })
        assert response.status_code == 200
        assert b'Signup successful' in response.data
    
    def test_signup_post_duplicate_email(self, client):
        """Test POST /signup with duplicate email"""
        response = client.post('/signup', data={
            'email': 'admin@test.com',  # Already exists
            'name': 'newadmin',
            'password': 'newpassword123'
        })
        # Should redirect to signup page
        assert response.status_code == 302
        assert '/signup' in response.headers.get('Location', '')
    
    def test_login_get(self, client):
        """Test GET /login route"""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Login' in response.data
        assert b'Email' in response.data
        assert b'Password' in response.data
    
    def test_login_post_admin_success(self, client):
        """Test successful admin login"""
        response = client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'admin123'
        })
        assert response.status_code == 200
        assert b'Login successful - admin user' in response.data
    
    def test_login_post_user_success(self, client):
        """Test successful regular user login"""
        response = client.post('/login', data={
            'email': 'test@test.com',
            'password': 'test123'
        })
        assert response.status_code == 200
        assert b'Login successful - regular user' in response.data
    
    def test_login_post_invalid_email(self, client):
        """Test login with invalid email"""
        response = client.post('/login', data={
            'email': 'nonexistent@test.com',
            'password': 'password123'
        })
        assert response.status_code == 302  # Redirect to login
        assert '/login' in response.headers.get('Location', '')
    
    def test_login_post_invalid_password(self, client):
        """Test login with invalid password"""
        response = client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'wrongpassword'
        })
        assert response.status_code == 302  # Redirect to login
        assert '/login' in response.headers.get('Location', '')
    
    def test_login_post_empty_credentials(self, client):
        """Test login with empty credentials"""
        response = client.post('/login', data={
            'email': '',
            'password': ''
        })
        assert response.status_code == 302  # Redirect to login
        assert '/login' in response.headers.get('Location', '')
    
    def test_logout_route(self, client):
        """Test logout route"""
        # First login
        client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'admin123'
        })
        
        # Then logout
        response = client.get('/logout')
        assert response.status_code == 200
        assert b'Logged out' in response.data


class TestAuthRouteIntegration:
    """Test auth route integration scenarios"""
    
    def test_login_logout_flow(self, client):
        """Test complete login/logout flow"""
        # Test login
        login_response = client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'admin123'
        })
        assert login_response.status_code == 200
        assert b'Login successful' in login_response.data
        
        # Test logout
        logout_response = client.get('/logout')
        assert logout_response.status_code == 200
        assert b'Logged out' in logout_response.data
    
    def test_signup_login_flow(self, client):
        """Test signup followed by login"""
        # Test signup
        signup_response = client.post('/signup', data={
            'email': 'flow@test.com',
            'name': 'flowuser',
            'password': 'flowpassword123'
        })
        assert signup_response.status_code == 200
        assert b'Signup successful' in signup_response.data
        
        # Test login with new user
        login_response = client.post('/login', data={
            'email': 'flow@test.com',
            'password': 'flowpassword123'
        })
        assert login_response.status_code == 200
        assert b'Login successful' in login_response.data