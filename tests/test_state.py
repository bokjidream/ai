import pytest
from pydantic import ValidationError

from graph.state import (
    DisabilitySeverity,
    EmploymentStatus,
    IncomeLevel,
    MaritalStatus,
    UserProfile,
    WelfareCandidate,
)


class TestUserProfile:
    def test_default_all_none(self):
        profile = UserProfile()
        assert profile.age is None
        assert profile.income_level is None
        assert profile.disability is None

    def test_is_elderly_true(self):
        assert UserProfile(age=65).is_elderly is True
        assert UserProfile(age=66).is_elderly is True

    def test_is_elderly_false(self):
        assert UserProfile(age=64).is_elderly is False

    def test_is_elderly_none_when_age_missing(self):
        assert UserProfile().is_elderly is None

    def test_income_level_enum(self):
        profile = UserProfile(income_level=IncomeLevel.BASIC)
        assert profile.income_level == "기초생활수급자"

    def test_employment_status_enum(self):
        profile = UserProfile(employment_status=EmploymentStatus.UNEMPLOYED)
        assert profile.employment_status == "실업"

    def test_marital_status_enum(self):
        profile = UserProfile(marital_status=MaritalStatus.SINGLE)
        assert profile.marital_status == "미혼"

    def test_disability_severity_enum(self):
        profile = UserProfile(
            disability=True, disability_severity=DisabilitySeverity.SEVERE
        )
        assert profile.disability_severity == "중증"

    def test_disability_severity_only_when_disabled(self):
        # disability=False면 severity는 None이어야 함
        profile = UserProfile(disability=False, disability_severity=None)
        assert profile.disability_severity is None

    def test_disability_severity_raises_when_not_disabled(self):
        with pytest.raises(ValidationError):
            UserProfile(disability=False, disability_severity=DisabilitySeverity.SEVERE)

    def test_extra_fields_default_empty(self):
        assert UserProfile().extra_fields == {}

    def test_extra_fields_store_values(self):
        profile = UserProfile(
            extra_fields={"deposit_amount": 50000000, "vehicle_owned": False}
        )
        assert profile.extra_fields["deposit_amount"] == 50000000
        assert profile.extra_fields["vehicle_owned"] is False

    def test_income_level_all_values(self):
        values = [e.value for e in IncomeLevel]
        assert "기초생활수급자" in values
        assert "차상위계층" in values
        assert "저소득" in values
        assert "일반" in values


class TestWelfareCandidate:
    def test_required_fields(self):
        candidate = WelfareCandidate(
            serv_id="WLF00000035",
            serv_nm="기초연금",
            serv_dgst="만 65세 이상 저소득 노인 연금",
        )
        assert candidate.serv_id == "WLF00000035"
        assert candidate.serv_nm == "기초연금"

    def test_defaults(self):
        candidate = WelfareCandidate(
            serv_id="WLF00000035",
            serv_nm="기초연금",
            serv_dgst="노인 연금",
        )
        assert candidate.score == 0.0
        assert candidate.priority == 0
        assert candidate.department == ""
        assert candidate.eligibility_reason == ""
        assert candidate.required_documents == []
        assert candidate.application_method == ""
        assert candidate.application_url is None
        assert candidate.detail_fetched is False

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            WelfareCandidate(serv_id="WLF00000035")

    def test_eligibility_reason_default_empty(self):
        candidate = WelfareCandidate(
            serv_id="WLF00000035",
            serv_nm="기초연금",
            serv_dgst="노인 연금",
        )
        assert candidate.eligibility_reason == ""
