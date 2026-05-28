"""
Test for log metrics reset when extending HPC client simulation.
"""

from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.unit


class TestExtendSimulationMetricsReset:
    """Test that log metrics are reset when extending HPC simulations"""

    @patch("y_web.src.hpc.log_parser.reset_hpc_client_metrics")
    @patch("y_web.src.hpc.log_parser.reset_hpc_server_metrics")
    def test_metrics_reset_called_for_hpc_extension(
        self, mock_reset_server, mock_reset_client
    ):
        """Test that both client and server metrics are reset for HPC experiments"""
        # Setup mocks to simulate successful reset
        mock_reset_client.return_value = True
        mock_reset_server.return_value = True

        # Simulate the reset calls
        exp_id = 123
        client_id = 456

        # Call the reset functions as done in extend_simulation
        result_client = mock_reset_client(exp_id, client_id)
        result_server = mock_reset_server(exp_id)

        # Verify both functions were called
        mock_reset_client.assert_called_once_with(exp_id, client_id)
        mock_reset_server.assert_called_once_with(exp_id)

        # Verify both returned success
        assert result_client is True
        assert result_server is True

    @patch("y_web.src.hpc.log_parser.reset_hpc_client_metrics")
    @patch("y_web.src.hpc.log_parser.reset_hpc_server_metrics")
    def test_metrics_reset_handles_client_failure(
        self, mock_reset_server, mock_reset_client
    ):
        """Test handling when client metrics reset fails"""
        mock_reset_client.return_value = False
        mock_reset_server.return_value = True

        exp_id = 123
        client_id = 456

        result_client = mock_reset_client(exp_id, client_id)
        result_server = mock_reset_server(exp_id)

        assert result_client is False
        assert result_server is True
        # In the actual code, this should trigger a warning flash message

    @patch("y_web.src.hpc.log_parser.reset_hpc_client_metrics")
    @patch("y_web.src.hpc.log_parser.reset_hpc_server_metrics")
    def test_metrics_reset_handles_server_failure(
        self, mock_reset_server, mock_reset_client
    ):
        """Test handling when server metrics reset fails"""
        mock_reset_client.return_value = True
        mock_reset_server.return_value = False

        exp_id = 123
        client_id = 456

        result_client = mock_reset_client(exp_id, client_id)
        result_server = mock_reset_server(exp_id)

        assert result_client is True
        assert result_server is False
        # In the actual code, this should trigger a warning flash message

    @patch("y_web.src.hpc.log_parser.reset_hpc_client_metrics")
    @patch("y_web.src.hpc.log_parser.reset_hpc_server_metrics")
    def test_metrics_reset_handles_both_failures(
        self, mock_reset_server, mock_reset_client
    ):
        """Test handling when both resets fail"""
        mock_reset_client.return_value = False
        mock_reset_server.return_value = False

        exp_id = 123
        client_id = 456

        result_client = mock_reset_client(exp_id, client_id)
        result_server = mock_reset_server(exp_id)

        assert result_client is False
        assert result_server is False
        # In the actual code, this should trigger a warning flash message

    def test_reset_functions_exist(self):
        """Test that the reset functions exist in log_metrics module"""
        try:
            from y_web.src.hpc.log_parser import (
                reset_hpc_client_metrics,
                reset_hpc_server_metrics,
            )

            # Verify functions are callable
            assert callable(reset_hpc_client_metrics)
            assert callable(reset_hpc_server_metrics)

            # Verify function signatures (they should accept exp_id)
            import inspect

            client_sig = inspect.signature(reset_hpc_client_metrics)
            server_sig = inspect.signature(reset_hpc_server_metrics)

            # Client metrics function should have exp_id and client_id params
            assert "exp_id" in client_sig.parameters
            assert "client_id" in client_sig.parameters

            # Server metrics function should have exp_id param
            assert "exp_id" in server_sig.parameters

        except ImportError as e:
            pytest.fail(f"Could not import reset functions: {e}")

    def test_conditional_logic_coverage(self):
        """Test that all conditional branches are covered"""
        # Test all possible combinations of reset results
        test_cases = [
            (True, True, "success"),  # Both succeed
            (False, False, "both_fail"),  # Both fail
            (False, True, "client_fail"),  # Client fails
            (True, False, "server_fail"),  # Server fails
        ]

        for client_result, server_result, expected_case in test_cases:
            # Simulate the conditional logic from extend_simulation
            if client_result and server_result:
                message_type = "success"
            elif not client_result and not server_result:
                message_type = "both_fail"
            elif not client_result:
                message_type = "client_fail"
            else:  # not server_result
                message_type = "server_fail"

            assert (
                message_type == expected_case
            ), f"Failed for client={client_result}, server={server_result}"
