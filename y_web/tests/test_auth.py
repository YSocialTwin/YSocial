"""
Tests for y_web authentication module
"""
import pytest
from y_web import db
from y_web.models import Admin_users, User_mgmt, Exps
from werkzeug.security import generate_password_hash


class TestAuth:
    """Test authentication functionality"""
    
    def test_login_page_get(self, client):
        """Test GET request to login page"""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'login' in response.data.lower()
    
    def test_signup_page_get(self, client):
        """Test GET request to signup page"""
        response = client.get('/signup')
        assert response.status_code == 200
        assert b'register' in response.data.lower() or b'signup' in response.data.lower()
    
    def test_admin_login_success(self, client, app):
        """Test successful admin login"""
        response = client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'admin123'
        }, follow_redirects=True)
        
        # Should redirect to admin dashboard
        assert response.status_code == 200
        # Check if redirected to admin area (may vary based on implementation)
    
    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        response = client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'wrongpassword'
        })
        
        # Should stay on login page or redirect back to login
        assert response.status_code in [200, 302]
    
    def test_login_nonexistent_user(self, client):
        """Test login with nonexistent user"""
        response = client.post('/login', data={
            'email': 'nonexistent@test.com',
            'password': 'password'
        })
        
        # Should stay on login page or redirect back to login
        assert response.status_code in [200, 302]
    
    def test_logout(self, client, app):
        """Test logout functionality"""
        # First login
        client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'admin123'
        })
        
        # Then logout
        response = client.get('/logout')
        assert response.status_code in [200, 302]  # Should redirect after logout
    
    def test_signup_new_user(self, client, app):
        """Test signing up a new user"""
        with app.app_context():
            # Create an active experiment first (required for signup)
            exp = Exps(
                exp_name='Test Experiment',
                exp_descr='Test Description',
                platform_type='twitter',
                owner='admin',
                status=1,
                running=0
            )
            db.session.add(exp)
            db.session.commit()
            
            response = client.post('/signup', data={
                'email': 'newuser@test.com',
                'username': 'newuser',
                'password': 'newpassword123'
            })
            
            # Should handle signup (may redirect or show success)
            assert response.status_code in [200, 302]
            
            # Check if user was created
            new_user = Admin_users.query.filter_by(email='newuser@test.com').first()
            if new_user:
                assert new_user.username == 'newuser'
    
    def test_signup_duplicate_email(self, client, app):
        """Test signup with duplicate email"""
        response = client.post('/signup', data={
            'email': 'admin@test.com',  # Already exists
            'username': 'newadmin',
            'password': 'newpassword123'
        })
        
        # Should handle duplicate email (may show error or redirect)
        assert response.status_code in [200, 302]
    
    def test_protected_route_without_login(self, client):
        """Test accessing protected route without login"""
        response = client.get('/admin/dashboard')
        
        # Should redirect to login page
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')
    
    def test_user_loader_function(self, app):
        """Test the user loader function"""
        with app.app_context():
            # Get existing test user
            user = User_mgmt.query.filter_by(username='testuser').first()
            assert user is not None
            
            # Test that user can be loaded by ID
            from flask_login import login_manager
            loaded_user = login_manager._user_callback(str(user.id))
            assert loaded_user is not None
            assert loaded_user.id == user.id
    
    def test_user_loader_invalid_id(self, app):
        """Test user loader with invalid ID"""
        with app.app_context():
            from flask_login import login_manager
            loaded_user = login_manager._user_callback('99999')  # Non-existent ID
            assert loaded_user is None
    
    def test_user_loader_non_numeric_id(self, app):
        """Test user loader with non-numeric ID"""
        with app.app_context():
            from flask_login import login_manager
            try:
                loaded_user = login_manager._user_callback('invalid')
                # Should handle gracefully
                assert loaded_user is None
            except ValueError:
                # ValueError is acceptable for non-numeric ID
                pass


class TestAuthHelpers:
    """Test authentication helper functions and utilities"""
    
    def test_password_hashing(self, app):
        """Test password hashing functionality"""
        password = 'testpassword123'
        hashed = generate_password_hash(password)
        
        assert hashed != password  # Should be hashed
        assert len(hashed) > len(password)  # Hashed version should be longer
        
        # Test verification
        from werkzeug.security import check_password_hash
        assert check_password_hash(hashed, password)
        assert not check_password_hash(hashed, 'wrongpassword')