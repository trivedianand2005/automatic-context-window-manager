def test_orders_require_authentication(client):
    assert client.get("/orders").status_code == 401


def test_place_and_list_orders(client, auth_headers):
    created = client.post("/orders", json={"product_id": 1, "quantity": 2}, headers=auth_headers)
    assert created.status_code == 201
    listed = client.get("/orders", headers=auth_headers)
    assert [o["quantity"] for o in listed.json()] == [2]


def test_unknown_product_returns_404(client, auth_headers):
    response = client.post("/orders", json={"product_id": 99, "quantity": 1}, headers=auth_headers)
    assert response.status_code == 404
