# PyInstaller Size Optimization

This document describes the strategies applied to reduce the PyInstaller executable size.

**IMPORTANT NOTE:** matplotlib, pandas, IPython, jupyter, notebook, jupyterlab, setuptools, pip, and wheel are **NOT** excluded from the build because they are required for YSocial's JupyterLab data science functionality.

## Optimization Strategies Applied

### 1. NLTK Data Minimization ✅
**Problem:** NLTK's full corpus is over 100MB  
**Solution:** Only include VADER lexicon (~1MB) since YSocial only uses `nltk.sentiment`

**Implementation:**
- Custom `hook-nltk.py` in `pyinstaller_hooks/`
- Modified spec file with **3-method fallback approach** for robust VADER collection:
  1. Try `collect_data_files()` with multiple subdir patterns
  2. Manual discovery via NLTK data paths
  3. Use `nltk.data.find()` with proper path handling
  4. Final fallback: collect all sentiment data
- Hidden imports limited to `nltk.sentiment.vader`
- Verbose logging during build to confirm VADER collection

**Size Savings:** ~99MB

### 2. Excluded Unnecessary Packages ✅
**Excluded packages:**
- pytest, unittest (testing frameworks)
- sphinx, docutils (documentation)
- Unused NLTK modules (parsing, translation, etc.)
- Unused visualization: seaborn, plotly, bokeh

**RETAINED packages (needed for JupyterLab):**
- matplotlib, pandas (data visualization and analysis)
- IPython, jupyter, notebook, jupyterlab (interactive computing)
- setuptools, pip, wheel (package management for notebook extensions)

**Size Savings:** ~20-30MB (from excluded packages only)

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
- Expected size: 400-600MB (~25% reduction)
- NLTK data: ~1MB (99% reduction)
- Only necessary packages included
- JupyterLab and data science packages retained for functionality

**Note:** The size reduction is more modest (~25% vs originally estimated 50%) because matplotlib, pandas, IPython, jupyter, notebook, jupyterlab, setuptools, pip, and wheel are required for YSocial's JupyterLab data science functionality and must be included.

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
**Cause:** VADER lexicon was not included in the bundle during PyInstaller build

**Solutions:**
1. **Before building:** Ensure VADER lexicon is downloaded
   ```bash
   python -c "import nltk; nltk.download('vader_lexicon')"
   ```

2. **Check build output:** Look for VADER collection messages during `pyinstaller y_social.spec`
   - `✓ Method 1 SUCCESS` = collect_data_files worked
   - `✓ Method 2 SUCCESS` = manual discovery worked
   - `✓ Method 3 SUCCESS` = nltk.data.find worked
   - `✓ FALLBACK SUCCESS` = collected all sentiment data
   - `⚠ WARNING: Could not collect VADER lexicon` = build will fail at runtime

3. **If collection fails:** Check NLTK data location
   ```bash
   python -c "import nltk; print(nltk.data.path)"
   ```
   Ensure vader_lexicon exists in one of these paths under `sentiment/` or `corpora/`

4. **Manual addition:** Add to spec file manually if auto-detection fails
   ```python
   datas += [('/path/to/nltk_data/sentiment/vader_lexicon.zip', 'nltk_data/sentiment')]
   ```

### "⚠ No VADER lexicon data found via collect_data_files"
**This is expected** - it means Method 1 failed but the build tries Methods 2-4 automatically. Check for subsequent success messages.

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
