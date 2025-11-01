# Security Upgrade Quick Reference

**Quick guide for upgrading vulnerable dependencies in YSocial**

---

## Quick Commands

### 1. Upgrade Core Dependencies (Flask, Werkzeug, Jinja2)
```bash
pip install --upgrade 'Flask>=3.0.3' 'Werkzeug>=3.0.3' 'Jinja2>=3.1.4'
python run_tests.py
```

### 2. Upgrade Security Libraries (cryptography, pyOpenSSL)
```bash
pip install --upgrade 'cryptography>=42.0.8' 'pyOpenSSL>=24.3.0'
python run_tests.py
```

### 3. Pin Previously Unpinned Packages
```bash
pip install --upgrade 'pillow>=10.4.0' 'requests>=2.32.3'
python run_tests.py
```

---

## Current Vulnerabilities Summary

| Package | Current | Required | Severity | CVEs |
|---------|---------|----------|----------|------|
| Flask | 2.1.2 | ≥3.0.3 | HIGH | CVE-2023-30861, CVE-2023-25577 |
| Werkzeug | 2.1.2 | ≥3.0.3 | HIGH | CVE-2023-25577, CVE-2023-46136 |
| cryptography | 37.0.2 | ≥42.0.8 | HIGH | CVE-2023-23931, CVE-2024-26130 |
| Jinja2 | 3.1.2 | ≥3.1.4 | MEDIUM | CVE-2024-34064 |
| pyOpenSSL | 22.0.0 | ≥24.3.0 | MEDIUM | Multiple OpenSSL CVEs |
| pillow | unpinned | ≥10.4.0 | MEDIUM | Multiple image processing CVEs |
| requests | unpinned | ≥2.32.3 | MEDIUM | CVE-2024-35195 |

---

## Testing Checklist

### Before Upgrade
- [ ] Run full test suite: `python run_tests.py`
- [ ] Expected: 7/7 test files passing, 69 individual tests
- [ ] Save current versions: `pip freeze > requirements_backup.txt`

### After Each Upgrade Phase
- [ ] Run full test suite: `python run_tests.py`
- [ ] Run security tests: `pytest y_web/tests/test_security_upgrades.py -v`
- [ ] Check for deprecation warnings
- [ ] Test manual login/signup
- [ ] Test admin dashboard

### Manual Testing
- [ ] User registration works
- [ ] User login works
- [ ] Admin dashboard accessible
- [ ] Create agent/population works
- [ ] Social interactions work (follow, share, react)
- [ ] PostgreSQL connection works (if using PostgreSQL)

---

## Quick Rollback

```bash
# If issues occur:
pip install -r requirements_backup.txt
python run_tests.py
```

---

## Updated requirements.txt

Replace the vulnerable packages in `requirements.txt` with:

```txt
# Core Framework (UPGRADED)
Flask>=3.0.3
Flask-Login>=0.6.3
Flask-SQLAlchemy>=3.0.0
WTForms>=3.1.0

# Template Engine (UPGRADED)
Jinja2>=3.1.4
MarkupSafe>=2.1.5

# Web Server (UPGRADED)
Werkzeug>=3.0.3
itsdangerous>=2.2.0
click>=8.1.7

# Security (UPGRADED)
cryptography>=42.0.8
pyOpenSSL>=24.3.0

# HTTP Client (NOW PINNED)
requests>=2.32.3

# Image Processing (NOW PINNED)
pillow>=10.4.0

# Keep all other dependencies as they are...
```

---

## Breaking Changes to Watch For

### Flask 3.0
- ✅ Blueprint registration: No changes needed
- ✅ Configuration: No changes needed
- ✅ URL routing: No changes needed
- ⚠️ Some deprecated APIs removed (check warnings)

### Werkzeug 3.0
- ✅ Routing works the same
- ✅ Security utilities work the same
- ⚠️ Debug mode PIN generation changed (development only)

### Others
- ✅ Jinja2 3.1.4: Mostly backward compatible
- ✅ cryptography 42.x: API mostly compatible
- ✅ All other upgrades: Minimal breaking changes

---

## Success Criteria

✅ All 69 existing tests passing  
✅ All 21 security validation tests passing  
✅ No security vulnerabilities remaining  
✅ Manual testing checklist completed  
✅ No performance regression  

---

## Need Help?

See the full evaluation document: `DEPENDABOT_SECURITY_EVALUATION.md`

**Key sections:**
- Section 4: Detailed upgrade strategy
- Section 5: Risk assessment
- Section 8: Expected behavior changes
- Section 10: Full recommendations

---

**Last Updated:** January 2025  
**Status:** Ready for Implementation
