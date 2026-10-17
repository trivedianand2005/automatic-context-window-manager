def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_products(client):
    response = client.get("/products")
    assert response.json() == [{"id": 1, "name": "Demo Widget", "price_cents": 1999}]
