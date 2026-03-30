"""
Models for OTLP validation in Watchdog.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


from pydantic import BaseModel, ConfigDict

class OtlpValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str | None = None
