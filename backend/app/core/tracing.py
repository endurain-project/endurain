import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_tracing(app):
    # Check if Jaeger tracing is enabled using the 'JAEGER_ENABLED' environment variable
    if os.environ.get("JAEGER_ENABLED", "false") == "true":
        # Configure OpenTelemetry with a specified service name
        trace.set_tracer_provider(
            TracerProvider(resource=Resource.create({"service.name": "backend_api"}))
        )
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=os.environ.get("JAEGER_PROTOCOL", "http")
                    + "://"
                    + os.environ.get("JAEGER_HOST", "jaeger")
                    + ":"
                    + os.environ.get("JAEGER_PORT", "4317")
                )
            )
        )


    # Instrument FastAPI app
    FastAPIInstrumentor.instrument_app(app)