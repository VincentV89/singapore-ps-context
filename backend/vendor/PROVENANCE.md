The following source files are copied unchanged from
[aws/context-ontology-accelerator](https://github.com/aws/context-ontology-accelerator)
at commit `c84a3043a989c30fe33658c763f5f279c6981aba` (v0.3.4),
under Apache-2.0. Copyright and SPDX headers are retained. The upstream
license is included as `LICENSE`.

| Vendored file | Upstream path |
| --- | --- |
| `serializer.py` | `packages/ontology-engine/src/coa_ontology/inducer/unstructured/services/serializer.py` |
| `coa_serve/tier3/graph_traverser.py` | `packages/context-manager/src/coa_serve/tier3/graph_traverser.py` |
| `coa_serve/query_utils.py` | `packages/context-manager/src/coa_serve/query_utils.py` |
| `coa_serve/clients/base.py` | `packages/context-manager/src/coa_serve/clients/base.py` |
| `coa_common/constants.py` | `libs/common/src/coa_common/constants.py` |

`coa_common/__init__.py` is a demo packaging shim that exposes only the
upstream namespace validator, avoiding the full accelerator's unrelated SDK
imports. Empty `coa_serve` package initializers are demo packaging scaffolding.
The actual vendored implementation files are unmodified.

`build_graph.py` invokes the upstream serializer to produce a schema-only
TBox, including its round-trip isomorphism check. Synthetic instances are a
separate Turtle artifact. `engine.py` invokes the upstream GraphTraverser
against a local RDFLib adapter with named graphs. Its async GraphClient
protocol is satisfied by the adapter; query bindings are flat strings as
expected upstream. Neptune-provided RDF/RDFS prefixes are supplied via
RDFLib's `initNs`.

This demo does not deploy the accelerator's ontology extraction, Neptune,
vector retrieval, connector, or full serve stacks. The included ontology can
be imported into the full accelerator later.
