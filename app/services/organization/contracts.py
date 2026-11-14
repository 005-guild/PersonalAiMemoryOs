"""Small public contracts and stable workflow fingerprints."""
import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.services.zhihu_sync.storage import safe_path


class OrganizationError(RuntimeError):
    @property
    def code(self):
        return str(self)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


class OrganizationSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    input_dir: str = ''
    output_dir: str = ''
    profile_id: str = 'deepseek'
    enabled: bool = False
    initial_budget_yuan: int = Field(default=20, ge=1, le=10000)
    monthly_budget_yuan: int = Field(default=10, ge=1, le=10000)
    taxonomy: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def paths(self):
        for value in (self.input_dir, self.output_dir):
            if value and (not Path(value).is_absolute() or len(value)>2048):
                raise ValueError('absolute_path_required')
            if value:
                safe_path(Path(value))
        if self.input_dir and self.output_dir:
            source, target = Path(self.input_dir).resolve(), Path(self.output_dir).resolve()
            if source.is_relative_to(target) or target.is_relative_to(source):
                raise ValueError('directories_overlap')
        for category in self.taxonomy:
            pieces = category.split('/')
            if len(pieces)!=2 or any(not x.strip() or len(x)>30 or x in {'.','..'} or any(c in x for c in '\\:*?"<>|\r\n') for x in pieces):
                raise ValueError('invalid_category')
        if len(set(self.taxonomy)) != len(self.taxonomy):
            raise ValueError('duplicate_category')
        return self


class OrganizationWrite(OrganizationSettings):
    expected_revision: str


class ProfileSwitch(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    profile_id: str=Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    expected_revision: str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_profile_fingerprint: str=Field(pattern=r'^[a-f0-9]{64}$')


def policy(config):
    return fingerprint({k:v for k,v in config.items() if k not in {'enabled','initial_budget_yuan','monthly_budget_yuan'}})
