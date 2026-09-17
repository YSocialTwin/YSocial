# Vendor Libraries

This directory contains third-party libraries bundled locally to ensure YSocial works without an internet connection.

## Purpose

When WiFi is turned off, external CDN resources become unavailable, causing critical functionality like data tables to break. By hosting these libraries locally, YSocial can function fully offline.

## Libraries Included

### JavaScript
- **jquery-3.6.0.min.js** - jQuery library for DOM manipulation and AJAX
- **chart.min.js** - Chart.js for data visualization
- **gridjs.umd.js** - Grid.js for interactive data tables

### CSS
- **bootstrap.min.css** - Bootstrap 4.5.2 CSS framework
- **gridjs-mermaid.min.css** - Grid.js Mermaid theme

### Icon Fonts
- **fontisto/** - Fontisto icon font library
- **mdi/** - Material Design Icons font library

## Version Information

- jQuery: 3.6.0
- Chart.js: 4.4.0
- Grid.js: 6.0.6
- Bootstrap: 4.5.2
- Fontisto: 3.0.4
- Material Design Icons: 7.2.96

## Updating Libraries

To update these libraries:

1. Update the version in `/tmp/vendor-libs/package.json`
2. Run `npm install`
3. Copy the new files to this directory
4. Update the version information in this README

## License

Each library maintains its own license. Please refer to the respective library's documentation for licensing information.
