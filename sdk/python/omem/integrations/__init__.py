"""Adapters that let other agent frameworks use OMEM as their memory.

Each adapter imports its framework lazily and none is imported here, so
installing OMEM never drags in a framework you do not use and the SDK keeps its
"no third-party dependencies" promise.
"""
