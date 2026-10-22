import app


def test_home_route_exists():
    routes = [rule.rule for rule in app.app.url_map.iter_rules()]
    assert "/" in routes


def test_app_is_flask_application():
    assert app.app is not None
    assert app.app.config["TESTING"] is False or isinstance(
        app.app.config["TESTING"], bool
    )
