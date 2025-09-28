"""
Tests for y_web main module
"""
import pytest
from y_web import db
from y_web.models import Admin_users, User_mgmt, Page, Agent
from y_web.main import get_safe_profile_pic, is_admin
from werkzeug.security import generate_password_hash


class TestMainHelpers:
    """Test helper functions in main module"""
    
    def test_get_safe_profile_pic_page(self, app):
        """Test get_safe_profile_pic for pages"""
        with app.app_context():
            # Create a test page
            page = Page(
                name='testpage',
                descr='Test page description',
                page_type='news',
                feed='',
                keywords='test',
                logo='test_logo.png',
                pg_type='page',
                leaning='neutral'
            )
            db.session.add(page)
            db.session.commit()
            
            # Test getting profile pic for page
            logo = get_safe_profile_pic('testpage', is_page=1)
            assert logo == 'test_logo.png'
    
    def test_get_safe_profile_pic_page_no_logo(self, app):
        """Test get_safe_profile_pic for page without logo"""
        with app.app_context():
            # Create a test page without logo
            page = Page(
                name='testpage2',
                descr='Test page description',
                page_type='news',
                feed='',
                keywords='test',
                pg_type='page',
                leaning='neutral'
            )
            db.session.add(page)
            db.session.commit()
            
            # Test getting profile pic for page without logo
            logo = get_safe_profile_pic('testpage2', is_page=1)
            assert logo == ''
    
    def test_get_safe_profile_pic_nonexistent_page(self, app):
        """Test get_safe_profile_pic for nonexistent page"""
        with app.app_context():
            logo = get_safe_profile_pic('nonexistentpage', is_page=1)
            assert logo == ''
    
    def test_get_safe_profile_pic_admin_user(self, app):
        """Test get_safe_profile_pic for admin user"""
        with app.app_context():
            # Create admin user with profile pic
            admin = Admin_users(
                username='profileadmin',
                email='profileadmin@test.com',
                password=generate_password_hash('admin123'),
                role='admin',
                last_seen='2023-01-01',
                profile_pic='admin_pic.png'
            )
            db.session.add(admin)
            db.session.commit()
            
            # Test getting profile pic for admin user
            pic = get_safe_profile_pic('profileadmin', is_page=0)
            assert pic == 'admin_pic.png'
    
    def test_get_safe_profile_pic_admin_user_no_pic(self, app):
        """Test get_safe_profile_pic for admin user without profile pic"""
        with app.app_context():
            pic = get_safe_profile_pic('admin', is_page=0)  # admin from conftest
            assert pic == ''  # No profile pic set in conftest
    
    def test_get_safe_profile_pic_nonexistent_user(self, app):
        """Test get_safe_profile_pic for nonexistent user"""
        with app.app_context():
            pic = get_safe_profile_pic('nonexistentuser', is_page=0)
            assert pic == ''
    
    def test_is_admin_true(self, app):
        """Test is_admin function with admin user"""
        with app.app_context():
            result = is_admin('admin')  # admin from conftest
            assert result is True
    
    def test_is_admin_false(self, app):
        """Test is_admin function with non-admin user"""
        with app.app_context():
            # Create a non-admin user
            user = Admin_users(
                username='normaluser',
                email='normal@test.com',
                password=generate_password_hash('password'),
                role='user',
                last_seen='2023-01-01'
            )
            db.session.add(user)
            db.session.commit()
            
            result = is_admin('normaluser')
            assert result is False
    
    def test_is_admin_nonexistent_user(self, app):
        """Test is_admin function with nonexistent user"""
        with app.app_context():
            # This should raise an AttributeError when trying to access role
            # on None object, but we test the current implementation
            try:
                result = is_admin('nonexistentuser')
                # If it doesn't raise an error, it should return False
                assert result is False
            except AttributeError:
                # Expected behavior when user is None
                pass


class TestMainRoutes:
    """Test main blueprint routes"""
    
    def test_main_routes_exist(self, app):
        """Test that main routes can be imported"""
        # This tests that the main blueprint is properly configured
        with app.app_context():
            # Test that we can access the main blueprint
            from y_web.main import main
            assert main is not None
            assert main.name == 'main'
    
    def test_main_blueprint_registration(self, app):
        """Test that main blueprint is registered with the app"""
        with app.app_context():
            # Check if main blueprint is registered
            blueprint_names = [bp.name for bp in app.iter_blueprints()]
            assert 'main' in blueprint_names


class TestMainUtilities:
    """Test utility functions and edge cases in main module"""
    
    def test_empty_username_handling(self, app):
        """Test handling of empty username in utility functions"""
        with app.app_context():
            # Test get_safe_profile_pic with empty username
            pic = get_safe_profile_pic('', is_page=0)
            assert pic == ''
            
            pic = get_safe_profile_pic('', is_page=1)
            assert pic == ''
    
    def test_none_username_handling(self, app):
        """Test handling of None username in utility functions"""
        with app.app_context():
            # Test get_safe_profile_pic with None username
            pic = get_safe_profile_pic(None, is_page=0)
            assert pic == ''
            
            pic = get_safe_profile_pic(None, is_page=1)
            assert pic == ''