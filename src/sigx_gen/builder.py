"""Mutable signature builder used by transform callbacks."""

from __future__ import annotations

from sigx_gen.signature_ir import ParamKind, SignatureIR, SigParam


class SignatureBuilder:
    """Mutable helper for building transformed signatures."""

    def __init__(
        self,
        params: list[SigParam],
        return_annotation: str | None,
        is_async: bool,
        type_params: tuple[str, ...],
    ) -> None:
        """Initialize the builder.

        Args:
            params: Mutable parameter list.
            return_annotation: Return annotation string.
            is_async: Whether the target is async.
            type_params: Function-level type parameter declarations.
        """
        self._params = params
        self._return_annotation = return_annotation
        self._is_async = is_async
        self._type_params = type_params
        self._validate_unique_names()

    @classmethod
    def from_signature(cls, sig: SignatureIR) -> SignatureBuilder:
        """Create a mutable builder from immutable signature IR.

        Args:
            sig: Source immutable signature.

        Returns:
            A new builder seeded from ``sig``.
        """
        return cls(
            params=list(sig.params),
            return_annotation=sig.return_annotation,
            is_async=sig.is_async,
            type_params=sig.type_params,
        )

    def add_kwonly(
        self,
        name: str,
        *,
        annotation: str = "Any",
        default: str | None = "...",
        if_missing: bool = False,
    ) -> None:
        """Insert a keyword-only parameter.

        Args:
            name: Parameter name.
            annotation: Annotation source.
            default: Default source expression.
            if_missing: Skip insertion when ``name`` already exists.

        Raises:
            ValueError: If duplicates exist and ``if_missing`` is false.
        """
        existing = self._index_of(name)
        if existing is not None:
            if if_missing:
                return
            raise ValueError(f"parameter already exists: {name}")

        insert_at = self._kwonly_insert_index()
        self._params.insert(
            insert_at,
            SigParam(name=name, kind=ParamKind.KW_ONLY, annotation=annotation, default=default),
        )
        self._validate_unique_names()

    def remove(self, name: str) -> None:
        """Remove a parameter by name.

        Args:
            name: Parameter name.

        Raises:
            ValueError: If parameter is missing or unsupported for removal.
        """
        index = self._index_of(name)
        if index is None:
            raise ValueError(f"parameter not found: {name}")

        kind = self._params[index].kind
        if kind in {ParamKind.VAR_POS, ParamKind.VAR_KW}:
            raise ValueError("cannot remove variadic parameters in v0.1")

        self._params.pop(index)

    def rename(self, old: str, new: str) -> None:
        """Rename a parameter.

        Args:
            old: Existing parameter name.
            new: New parameter name.

        Raises:
            ValueError: If old does not exist or new already exists.
        """
        old_index = self._index_of(old)
        if old_index is None:
            raise ValueError(f"parameter not found: {old}")
        if self._index_of(new) is not None:
            raise ValueError(f"parameter already exists: {new}")

        old_param = self._params[old_index]
        self._params[old_index] = SigParam(
            name=new,
            kind=old_param.kind,
            annotation=old_param.annotation,
            default=old_param.default,
        )
        self._validate_unique_names()

    def set_return(self, annotation: str) -> None:
        """Set the return annotation.

        Args:
            annotation: Return annotation source expression.
        """
        self._return_annotation = annotation

    def build(self) -> SignatureIR:
        """Build immutable signature IR.

        Returns:
            A frozen signature object.
        """
        self._validate_unique_names()
        return SignatureIR(
            params=tuple(self._params),
            return_annotation=self._return_annotation,
            is_async=self._is_async,
            type_params=self._type_params,
        )

    def _index_of(self, name: str) -> int | None:
        for index, param in enumerate(self._params):
            if param.name == name:
                return index
        return None

    def _kwonly_insert_index(self) -> int:
        var_kw_index: int | None = None
        for index, param in enumerate(self._params):
            if param.kind == ParamKind.VAR_KW:
                var_kw_index = index
                break

        search_end = var_kw_index if var_kw_index is not None else len(self._params)
        last_kwonly_index: int | None = None
        for index in range(search_end):
            if self._params[index].kind == ParamKind.KW_ONLY:
                last_kwonly_index = index

        if last_kwonly_index is not None:
            return last_kwonly_index + 1
        if var_kw_index is not None:
            return var_kw_index
        return len(self._params)

    def _validate_unique_names(self) -> None:
        seen: set[str] = set()
        for param in self._params:
            if param.name in seen:
                raise ValueError(f"duplicate parameter name: {param.name}")
            seen.add(param.name)
