/*! map.js | Friendkit | © Css Ninja. 2019-2020 */

/* ==========================================================================
Map page functions
========================================================================== */

'use strict'

//Theme colors to be used from JS
var themeColors = {
  primary: '#3d70b2',
  secondary: '#41d6c3',
}

var map

var locations = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: {
        name: 'Dan Walker',
        logo: 'assets/img/avatars/dan.jpg',
        distance: 0.7,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.038659, 38.931567],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Ken Bogard',
        logo: 'assets/img/avatars/ken.jpg',
        distance: 0.9,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.04917572739542, 39.9294445481959],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Milly Augustine',
        logo: 'assets/img/avatars/milly.jpg',
        distance: 4.2,
      },
      geometry: {
        type: 'Point',
        coordinates: [-76.9898112710817, 38.8895342079819],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Edward Mayers',
        logo: 'assets/img/avatars/edward.jpeg',
        distance: 1.2,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.00479301834466, 38.877053582287495],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Elise Walker',
        logo: 'assets/img/avatars/elise.jpg',
        distance: 0.6,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.090372, 38.881189],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Gaelle Morris',
        logo: 'assets/img/avatars/gaelle.jpeg',
        distance: 1.8,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.01183574582745, 38.86857043885428],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Michael Baker',
        logo: 'assets/img/avatars/michael.jpg',
        distance: 2.6,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.03644340427914, 38.88124994936405],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Nelly Schwartz',
        logo: 'assets/img/avatars/nelly.png',
        distance: 1.3,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.0300660512461, 38.89122869283593],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Aline Kovalsky',
        logo: 'assets/img/avatars/aline.jpg',
        distance: 1.9,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.04021874884195, 38.89482356721561],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Cathy Wright',
        logo: 'assets/img/avatars/cathy.png',
        distance: 1.7,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.04474417208833, 38.89635248217012],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Bobby Brown',
        logo: 'assets/img/avatars/bobby.jpg',
        distance: 3.1,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.0156464467101, 38.89509742773548],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Stella Bergmann',
        logo: 'assets/img/avatars/stella.jpg',
        distance: 1.8,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.0222336382688, 38.900405978408486],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Daniel Wellington',
        logo: 'assets/img/avatars/daniel.jpg',
        distance: 2.2,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.03608398758193, 38.905382162894846],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'David Kim',
        logo: 'assets/img/avatars/david.jpg',
        distance: 1.6,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.031706, 38.914581],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Lana Henrikssen',
        logo: 'assets/img/avatars/lana.jpeg',
        distance: 2.1,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.020945, 38.878241],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Mike Lasalle',
        logo: 'assets/img/avatars/mike.jpg',
        distance: 2.9,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.007481, 38.876516],
      },
    },
    {
      type: 'Feature',
      properties: {
        name: 'Rolf Krupp',
        logo: 'assets/img/avatars/rolf.jpg',
        distance: 1.4,
      },
      geometry: {
        type: 'Point',
        coordinates: [-77.03608398758193, 38.905382162894846],
      },
    },
  ],
}

function loadLayers() {
  map.addSource('places', {
    type: 'geojson',
    data: locations,
  })
  // Add a layer showing the places.
  map.addLayer({
    id: 'places',
    type: 'circle',
    source: 'places',
    paint: {
      'circle-color': themeColors.primary,
      'circle-radius': 6,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  })

  // Create a popup, but don't add it to the map yet.
  var popup = new mapboxgl.Popup({
    closeButton: false,
    closeOnClick: false,
  }) //.setHTML('<p>' + properties.description + '</p>')

  map.on('click', 'places', function (e) {
    var coordinates = e.features[0].geometry.coordinates.slice()
    var description = e.features[0].properties.description
    var name = e.features[0].properties.name
    var logo = e.features[0].properties.logo
    var distance = e.features[0].properties.distance

    // Ensure that if the map is zoomed out such that multiple
    // copies of the feature are visible, the popup appears
    // over the copy being pointed to.
    while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
      coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360
    }

    new mapboxgl.Popup()
      .setLngLat(coordinates)
      .setHTML(
        `
        <div class="map-box-location">
          <div class="map-box-header">
            <div class="media-flex-center">
              <div class="avatar-wrap">
                <img
                  class="avatar"
                  src="${
                    env === 'development'
                      ? logo
                      : 'https://via.placeholder.com/150x150'
                  }"
                  alt=""
                />
              </div>
              <div class="flex-meta">
                <span class="is-dark-heading">${name}</span>
                <span>${distance} mile(s)</span>
              </div>
            </div>
          </div>
        </div>
      `,
      )
      .addTo(map)
  })

  // Change the cursor to a pointer when the mouse is over the places layer.
  map.on('mouseenter', 'places', function () {
    map.getCanvas().style.cursor = 'pointer'
  })

  // Change it back to a pointer when it leaves.
  map.on('mouseleave', 'places', function () {
    map.getCanvas().style.cursor = ''
  })
}

function initMapBox() {
  var mapStyle = ''
  var storageTheme = window.localStorage.getItem('theme')
  var token =
    'pk.eyJ1IjoiY3NzbmluamEiLCJhIjoiY2toZW1nYm0zMDAxODJycXFzZ3g4cnZ6diJ9.9ebfrGREuwkauRr_afDTgA'
  var markerOptions = {
    color: 'red',
  }

  if (storageTheme === 'dark') {
    mapStyle = 'mapbox://styles/mapbox/dark-v10'
  } else {
    mapStyle = 'mapbox://styles/mapbox/light-v10'
  }

  if ($('#mapbox-1').length) {
    mapboxgl.accessToken = token
    map = new mapboxgl.Map({
      container: 'mapbox-1',
      style: mapStyle,
      center: [-77.04, 38.907],
      zoom: 12,
    })

    map.on('load', function () {
      loadLayers()
    })

    /*var marker = new mapboxgl.Marker(markerOptions)
      .setLngLat([-77.04, 38.907])
      .addTo(map);*/

    // Add the control to the map.
    var geocoder = new MapboxGeocoder({
      accessToken: mapboxgl.accessToken,
      mapboxgl: mapboxgl,
      marker: {
        color: themeColors.primary,
      },
    })

    document.getElementById('geocoder').appendChild(geocoder.onAdd(map))
  }
}

$(function () {
  initMapBox()

  $('.map-box').on('click', function () {
    $('.map-box').removeClass('is-active')
    $(this).addClass('is-active')
    var lat = $(this).attr('data-lat')
    var long = $(this).attr('data-long')
    var index = parseInt($(this).attr('data-feature'))

    const popup = document.getElementsByClassName('mapboxgl-popup')
    if (popup.length) {
      popup[0].remove()
    }

    map.flyTo({
      center: [lat, long],
      zoom: 15,
      bearing: 0,
      essential: true, // this animation is considered essential with respect to prefers-reduced-motion
    })

    var name = locations.features[index].properties.name
    var logo = locations.features[index].properties.logo
    var distance = locations.features[index].properties.distance

    var quickPopup = new mapboxgl.Popup({ closeOnClick: false })
      .setLngLat([lat, long])
      .setHTML(
        `
          <div class="map-box-location">
            <div class="map-box-header">
              <div class="media-flex-center">
                <div class="avatar-wrap">
                  <img
                    class="avatar"
                    src="${
                      env === 'development'
                        ? logo
                        : 'https://via.placeholder.com/150x150'
                    }"
                    alt=""
                  />
                </div>
                <div class="flex-meta">
                  <span class="is-dark-heading">${name}</span>
                  <span>${distance} mile(s)</span>
                </div>
              </div>
            </div>
          </div>
        `,
      )
      .addTo(map)
  })

  $(document).on('themeChange', function (e, selectedTheme) {
    console.log(selectedTheme)
    map.removeLayer('places')
    map.removeSource('places')
    if (selectedTheme === 'dark') {
      map.setStyle('mapbox://styles/mapbox/dark-v10')
    } else {
      map.setStyle('mapbox://styles/mapbox/light-v10')
    }
    map.on('style.load', () => {
      const waiting = () => {
        if (!map.isStyleLoaded()) {
          setTimeout(waiting, 1500)
        } else {
          map.addSource('places', {
            type: 'geojson',
            data: locations,
          })
          // Add a layer showing the places.
          map.addLayer({
            id: 'places',
            type: 'circle',
            source: 'places',
            paint: {
              'circle-color':
                selectedTheme === 'dark'
                  ? themeColors.primary
                  : themeColors.primary,
              'circle-radius': 6,
              'circle-stroke-width': 2,
              'circle-stroke-color': '#ffffff',
            },
          })

          // Create a popup, but don't add it to the map yet.
          var popup = new mapboxgl.Popup({
            closeButton: false,
            closeOnClick: false,
          }) //.setHTML('<p>' + properties.description + '</p>')

          map.on('click', 'places', function (e) {
            var coordinates = e.features[0].geometry.coordinates.slice()
            var description = e.features[0].properties.description

            // Ensure that if the map is zoomed out such that multiple
            // copies of the feature are visible, the popup appears
            // over the copy being pointed to.
            while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
              coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360
            }

            new mapboxgl.Popup()
              .setLngLat(coordinates)
              .setHTML(
                `
                  <div class="map-box-location">
                    <div class="map-box-header">
                      <div class="media-flex-center">
                        <div class="avatar-wrap">
                          <img
                            class="avatar"
                            src="${
                              env === 'development'
                                ? logo
                                : 'https://via.placeholder.com/150x150'
                            }"
                            alt=""
                          />
                        </div>
                        <div class="flex-meta">
                          <span class="is-dark-heading">${name}</span>
                          <span>${distance} mile(s)</span>
                        </div>
                      </div>
                    </div>
                  </div>
                `,
              )
              .addTo(map)
          })

          // Change the cursor to a pointer when the mouse is over the places layer.
          map.on('mouseenter', 'places', function () {
            map.getCanvas().style.cursor = 'pointer'
          })

          // Change it back to a pointer when it leaves.
          map.on('mouseleave', 'places', function () {
            map.getCanvas().style.cursor = ''
          })
        }
      }
      waiting()
    })
  })
})
