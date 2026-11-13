from y_web.routes.admin.sub.clients._crud import _build_hourly_activity_chart_series


def test_dict_weights_are_kept():
    idx, data = _build_hourly_activity_chart_series({"3": 0.5})
    assert idx[0] == "0" and len(data) == 24 and data[3] == 0.5 and data[4] == 0


def test_csv_profile_of_active_hours_from_instant_messaging():
    _, data = _build_hourly_activity_chart_series("0,1,2,23")
    assert data[0] == data[2] == data[23] == 1 and data[3] == 0


def test_list_and_unusable_values_do_not_raise():
    assert _build_hourly_activity_chart_series([1, "x"])[1][1] == 1
    assert _build_hourly_activity_chart_series(None)[1] == [0] * 24
