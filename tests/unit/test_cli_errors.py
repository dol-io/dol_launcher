from __future__ import annotations

import inspect

import pytest
import typer

from core.models import DolCtlError
from dolctl.cli import with_errors, _extract_ctx


_SENTINEL = object()


class TestExtractCtx:
    def test_returns_value_from_named_kwarg(self) -> None:
        def fn(ctx: typer.Context) -> None:
            ...

        sig = inspect.signature(fn)
        assert _extract_ctx(sig, (), {"ctx": _SENTINEL}) is _SENTINEL

    def test_returns_value_from_positional(self) -> None:
        def fn(ctx: typer.Context, name: str) -> None:
            ...

        sig = inspect.signature(fn)
        assert _extract_ctx(sig, (_SENTINEL, "x"), {}) is _SENTINEL

    def test_returns_none_when_signature_has_no_ctx(self) -> None:
        def fn(name: str) -> None:
            ...

        sig = inspect.signature(fn)
        assert _extract_ctx(sig, ("x",), {}) is None

    def test_returns_none_when_ctx_param_missing_from_args(self) -> None:
        def fn(ctx: typer.Context, name: str) -> None:
            ...

        sig = inspect.signature(fn)
        # `args` does not include the ctx slot at all
        assert _extract_ctx(sig, (), {"name": "x"}) is None


class TestWithErrorsNoCtx:
    def test_propagates_normal_return(self) -> None:
        @with_errors
        def fn(name: str) -> str:
            return name.upper()

        assert fn("x") == "X"

    def test_catches_dolctl_error_and_exits(self, capsys) -> None:
        @with_errors
        def fn(name: str) -> None:
            raise DolCtlError("bad: " + name)

        with pytest.raises(typer.Exit) as exit_info:
            fn("oops")
        captured = capsys.readouterr()
        assert "Error: bad: oops" in captured.err
        assert exit_info.value.exit_code == 1
