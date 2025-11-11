# PyInstaller Size Optimization

This document describes the strategies applied to reduce the PyInstaller executable size.

## Optimization Strategies Applied

### 1. NLTK Data Minimization ✅
**Problem:** NLTK's full corpus is over 100MB  
**Solution:** Only include VADER lexicon (~1MB) since YSocial only uses `nltk.sentiment`

**Implementation:**
- Custom `hook-nltk.py` in `pyinstaller_hooks/`
- Modified spec file to collect only `sentiment/vader_lexicon.zip`
- Hidden imports limited to `nltk.sentiment.vader`

**Size Savings:** ~99MB

### 2. Excluded Unnecessary Packages ✅
**Excluded packages:**
- matplotlib, pandas (data science - not used)
- pytest, unittest (testing frameworks)
- IPython, notebook, jupyter (development tools)
- setuptools, pip, wheel (packaging tools)
- sphinx, docutils (documentation)
- Unused NLTK modules (parsing, translation, etc.)

**Size Savings:** ~50-100MB depending on dependencies

### 3. Binary Stripping ✅
**Enabled:** `strip=True` in EXE configuration

**Effect:** Removes debug symbols from compiled binaries

**Size Savings:** ~10-20% of binary sizes

### 4. UPX Compression ✅
**Enabled:** `upx=True` with smart exclusions

**Excluded from UPX:**
- `vcruntime140.dll` (can cause runtime issues)
- `python*.dll` (already optimized)
- `Qt*.dll` (can cause GUI issues)

**Size Savings:** ~30-40% compression ratio

### 5. Minimal Submodule Collection ✅
**Changed:**
- From: `collect_submodules("nltk")` (all NLTK modules)
- To: `["nltk.sentiment", "nltk.sentiment.vader"]` (only needed modules)

**Size Savings:** ~20-30MB

## Expected Results

### Before Optimization:
- Typical size: 500-800MB
- NLTK data: ~100MB
- Many unused packages included

### After Optimization:
- Expected size: 200-400MB (50% reduction)
- NLTK data: ~1MB (99% reduction)
- Only necessary packages included

## Testing

To verify functionality after optimization:

```bash
# Build with PyInstaller
pyinstaller y_social.spec

# Test NLTK sentiment analysis
./dist/YSocial
# Navigate to a post and check sentiment scores

# Verify VADER lexicon is accessible
python -c "from y_web.utils.text_utils import vader_sentiment; print(vader_sentiment('This is great!'))"
```

## Maintenance

When updating NLTK or adding new NLTK features:

1. Check if new NLTK data is needed
2. Update `hook-nltk.py` to include required data
3. Update hidden imports in `y_social.spec`
4. Test sentiment analysis functionality

## Troubleshooting

### "Resource vader_lexicon not found"
**Solution:** Ensure `nltk_data/sentiment/vader_lexicon.zip` is in the bundle

### Executable crashes on startup
**Solution:** Check UPX exclusions, some DLLs don't compress well

### Import errors for NLTK
**Solution:** Add missing submodules to `hidden_imports` in spec file

## Additional Optimization Ideas (Future)

1. **Lazy loading**: Load NLTK only when sentiment analysis is used
2. **External data**: Store NLTK data separately and download on first run
3. **Alternative libraries**: Consider using smaller sentiment analysis libraries
4. **Split builds**: Create minimal and full builds
5. **Tree shaking**: More aggressive removal of unused code
