from app.models.cvm_financial import AssetCvmIssuer, CvmIssuer

ASSET_PAYLOAD = {
    "ticker": "AUTH3",
    "name": "Ativo",
    "asset_type": "STOCK",
    "currency": "BRL",
}


def test_common_user_reads_but_cannot_mutate_assets(client, asset_factory):
    asset = asset_factory()
    assert client.get("/assets").status_code == 200
    assert client.get(f"/assets/{asset.id}").status_code == 200
    assert client.post("/assets", json=ASSET_PAYLOAD).status_code == 403
    assert client.put(f"/assets/{asset.id}", json={"name": "X"}).status_code == 403
    assert client.delete(f"/assets/{asset.id}").status_code == 403


def test_common_user_cannot_link_issuer(client, asset_factory, db_session):
    asset = asset_factory()
    issuer = CvmIssuer(cnpj="12345678000190", cvm_code="12345", official_name="Emissor")
    db_session.add(issuer)
    db_session.commit()
    assert (
        client.put(
            f"/intelligence/cvm/assets/{asset.id}/issuer",
            json={"issuer_id": str(issuer.id)},
        ).status_code
        == 403
    )
    assert db_session.query(AssetCvmIssuer).count() == 0


def test_superuser_can_mutate(client, active_user, db_session):
    active_user.is_superuser = True
    db_session.commit()
    created = client.post("/assets", json=ASSET_PAYLOAD)
    assert created.status_code == 201
    assert client.delete(f"/assets/{created.json()['id']}").status_code == 204


def test_unauthenticated_mutation_is_401(unauthenticated_client):
    assert unauthenticated_client.post("/assets", json=ASSET_PAYLOAD).status_code == 401
