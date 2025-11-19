"""Tests for configuration loading and management."""

import pytest
from pathlib import Path
import tempfile
import yaml

from holocene.config.loader import (
    Config,
    MercadoLivreConfig,
    load_config,
    save_config,
)


def test_mercadolivre_config_defaults():
    """Test MercadoLivreConfig has correct defaults."""
    config = MercadoLivreConfig()

    assert config.enabled is False
    assert config.client_id is None
    assert config.client_secret is None
    assert config.redirect_uri == "https://127.0.0.1:8080/auth/callback"
    assert config.access_token is None
    assert config.refresh_token is None
    assert config.token_expires_at is None
    assert config.auto_sync is False
    assert config.sync_interval_hours == 24
    assert config.auto_classify is True
    assert config.classify_as_web is True


def test_config_includes_mercadolivre():
    """Test that Config model includes mercadolivre section."""
    config = Config()

    # Should have mercadolivre attribute
    assert hasattr(config, 'mercadolivre')
    assert isinstance(config.mercadolivre, MercadoLivreConfig)

    # Should have defaults
    assert config.mercadolivre.enabled is False


def test_load_config_with_mercadolivre():
    """Test loading config with mercadolivre section from YAML."""
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        config_data = {
            'mercadolivre': {
                'enabled': True,
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret',
                'redirect_uri': 'https://example.com/callback',
                'auto_sync': True,
                'auto_classify': False,
            }
        }
        yaml.dump(config_data, f)
        temp_path = Path(f.name)

    try:
        # Load config
        config = load_config(temp_path)

        # Verify mercadolivre section loaded correctly
        assert config.mercadolivre.enabled is True
        assert config.mercadolivre.client_id == 'test_client_id'
        assert config.mercadolivre.client_secret == 'test_client_secret'
        assert config.mercadolivre.redirect_uri == 'https://example.com/callback'
        assert config.mercadolivre.auto_sync is True
        assert config.mercadolivre.auto_classify is False

    finally:
        # Cleanup
        temp_path.unlink()


def test_save_config_with_mercadolivre():
    """Test saving config with mercadolivre section."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / 'test_config.yml'

        # Create config with mercadolivre settings
        config = Config()
        config.mercadolivre.enabled = True
        config.mercadolivre.client_id = 'test_id'
        config.mercadolivre.client_secret = 'test_secret'

        # Save config
        save_config(config, config_path)

        # Load back and verify
        loaded_config = load_config(config_path)

        assert loaded_config.mercadolivre.enabled is True
        assert loaded_config.mercadolivre.client_id == 'test_id'
        assert loaded_config.mercadolivre.client_secret == 'test_secret'


def test_load_config_without_mercadolivre():
    """Test loading config file that doesn't have mercadolivre section (defaults)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        # Config with other sections but no mercadolivre
        config_data = {
            'privacy': {
                'tier': 'local_only'
            }
        }
        yaml.dump(config_data, f)
        temp_path = Path(f.name)

    try:
        config = load_config(temp_path)

        # Should have mercadolivre with defaults
        assert hasattr(config, 'mercadolivre')
        assert config.mercadolivre.enabled is False

    finally:
        temp_path.unlink()


def test_mercadolivre_config_validation():
    """Test that MercadoLivreConfig validates types correctly."""
    # Valid config
    valid_config = MercadoLivreConfig(
        enabled=True,
        client_id="123",
        sync_interval_hours=12
    )
    assert valid_config.enabled is True
    assert valid_config.sync_interval_hours == 12

    # Invalid type should raise validation error
    with pytest.raises(Exception):  # Pydantic ValidationError
        MercadoLivreConfig(enabled="not_a_bool")
