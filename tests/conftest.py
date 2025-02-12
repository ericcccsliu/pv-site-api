""" Pytest fixtures for tests """
import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pvsite_datamodel.sqlmodels import (
    Base,
    ClientSQL,
    ForecastSQL,
    ForecastValueSQL,
    GenerationSQL,
    SiteSQL,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

from pv_site_api.main import app
from pv_site_api.session import get_session


@pytest.fixture(scope="session")
def engine():
    """Make database engine"""
    with PostgresContainer("postgres:14.5") as postgres:
        url = postgres.get_connection_url()
        os.environ["DB_URL"] = url
        engine = create_engine(url)
        Base.metadata.create_all(engine)

        yield engine

        os.environ["DB_URL"] = "not-set"


@pytest.fixture(scope="function", autouse=True)
def db_session(engine):
    """Returns an sqlalchemy session, and after the test tears down everything properly."""
    connection = engine.connect()
    # begin the nested transaction
    transaction = connection.begin()
    # use the connection with the already started transaction

    with Session(bind=connection) as session:
        yield session

        session.close()
        # roll back the broader transaction
        transaction.rollback()
        # put back the connection to the connection pool
        connection.close()
        session.flush()

    engine.dispose()


@pytest.fixture()
def sites(db_session):
    """Create some fake sites"""
    sites = []
    for i in range(0, 4):
        client = ClientSQL(
            client_name=f"testclient_{i}",
        )

        db_session.add(client)
        db_session.commit()

        site = SiteSQL(
            client_uuid=client.client_uuid,
            client_site_id=i,
            client_site_name=f"sites_i{i+1000}",
            latitude=51,
            longitude=3,
            capacity_kw=4,
            ml_id=i,
        )

        db_session.add(site)
        db_session.commit()

        sites.append(site)

    return sites


@pytest.fixture()
def generations(db_session, sites):
    """Create some fake generations"""
    start_times = [datetime.today() - timedelta(minutes=x) for x in range(10)]

    all_generations = []
    for site in sites:
        for i in range(0, 10):
            generation = GenerationSQL(
                site_uuid=site.site_uuid,
                generation_power_kw=i,
                start_utc=start_times[i],
                end_utc=start_times[i] + timedelta(minutes=5),
            )
            all_generations.append(generation)

    db_session.add_all(all_generations)
    db_session.commit()

    return all_generations


@pytest.fixture()
def fake():
    """Set up ENV VAR FAKE to 1"""
    os.environ["FAKE"] = "1"

    yield

    os.environ["FAKE"] = "0"


@pytest.fixture()
def client_sql(db_session):
    """Make fake client sql"""
    client = ClientSQL(client_name="test_client")
    db_session.add(client)
    db_session.commit()


@pytest.fixture()
def forecast_values(db_session, sites):
    """Create some fake forecast values"""
    forecast_values = []
    forecast_version: str = "0.0.0"

    num_forecasts = 10
    num_values_per_forecast = 11

    timestamps = [datetime.utcnow() - timedelta(minutes=10 * i) for i in range(num_forecasts)]

    # To make things trickier we make a second forecast at the same for one of the timestamps.
    timestamps = timestamps + timestamps[-1:]

    for site in sites:
        for timestamp in timestamps:
            forecast: ForecastSQL = ForecastSQL(
                site_uuid=site.site_uuid, forecast_version=forecast_version, timestamp_utc=timestamp
            )

            db_session.add(forecast)
            db_session.commit()

            for i in range(num_values_per_forecast):
                # Forecasts of 15 minutes.
                duration = 15
                horizon = duration * i
                forecast_value: ForecastValueSQL = ForecastValueSQL(
                    forecast_power_kw=i,
                    forecast_uuid=forecast.forecast_uuid,
                    start_utc=timestamp + timedelta(minutes=horizon),
                    end_utc=timestamp + timedelta(minutes=horizon + duration),
                    horizon_minutes=horizon,
                )

                forecast_values.append(forecast_value)

    db_session.add_all(forecast_values)
    db_session.commit()

    return forecast_values


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app)
