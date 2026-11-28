from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def create_financial_income_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.post('/api/dividends/tax-benefit-preview')
    async def dividend_tax_benefit_preview(request: Request) -> JSONResponse:
        username = runtime.get_current_username(request)
        from app.services.tax.what_if import FinancialIncomeWhatIfError
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) - {'owner', 'tax_year', 'selections', 'context_key'}:
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_REQUEST_INVALID')
            owner = body.get('owner', '모두')
            year = body.get('tax_year', runtime.datetime.now(runtime.ZoneInfo('Asia/Seoul')).year)
            if not isinstance(owner, str) or not owner.strip():
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_OWNER_INVALID')
            if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_YEAR_INVALID')
            choices = body.get('selections', {})
            if not isinstance(choices, dict) or len(choices) > 500 or (owner == '모두' and choices):
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_SELECTION_INVALID')
            full = runtime.get_dashboard(username=username)
            # Resolve owner from authenticated holdings; never accept client events,
            # official verdicts, gross amounts, or a client username.
            context = runtime._dividend_benefit_context({}, full, username=username, owner=owner, tax_year=year)
            if context.get('invalid_owner'):
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_OWNER_INVALID')
            if choices and body.get('context_key') != context['context_key']:
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_CONTEXT_CHANGED')
            account_owners = {a['id']: a.get('owner') for a in full.get('accounts', [])}
            holdings = [h for h in full.get('holdings', [])
                if str(h.get('owner') or account_owners.get(h.get('account_id')) or '') == owner]
            summary = await runtime.get_web_dividend_summary(holdings,
                fx_rate=full.get('fx_rates', {}).get('USD', 1385.0), username=username) if owner != '모두' else {}
            result = runtime._dividend_benefit_context(summary, full, username=username, owner=owner,
                tax_year=year, selections=body.get('selections'))
        except (FinancialIncomeWhatIfError, ValueError) as exc:
            code = str(exc) if isinstance(exc, FinancialIncomeWhatIfError) else 'DIVIDEND_BENEFIT_REQUEST_INVALID'
            raise runtime.HTTPException(status_code=400, detail={'code': code}, headers={'Cache-Control': 'no-store'}) from None
        return runtime.JSONResponse(result, headers={'Cache-Control': 'no-store'})

    @router.get("/api/dividends/financial-income-family-risk")
    async def financial_income_family_risk(request: Request) -> JSONResponse:
        """Return per-family-member financial-income screening risk."""
        username = runtime.get_current_username(request)
        from app.services.tax import (
            FamilyFinancialIncomeRiskError,
            get_family_financial_income_risk_for_user,
        )
        try:
            result = await get_family_financial_income_risk_for_user(username)
        except FamilyFinancialIncomeRiskError as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": str(exc)},
                headers={"Cache-Control": "no-store"},
            ) from exc
        return runtime.JSONResponse(result, headers={"Cache-Control": "no-store"})

    @router.post("/api/dividends/financial-income-family-allocation-simulation")
    async def financial_income_family_allocation_simulation(request: Request) -> JSONResponse:
        """Compare a hypothetical family financial-income allocation without writes."""
        username = runtime.get_current_username(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": "FAMILY_ALLOCATION_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"}) from exc
        if (
            not isinstance(body, dict)
            or set(body) != {"allocations"}
            or not isinstance(body.get("allocations"), list)
        ):
            raise runtime.HTTPException(status_code=400, detail={"code": "FAMILY_ALLOCATION_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"})
        from app.services.tax import (
            FamilyFinancialIncomeAllocationError,
            get_family_financial_income_allocation_simulation_for_user,
        )
        try:
            result = await get_family_financial_income_allocation_simulation_for_user(
                username, allocations=body["allocations"]
            )
        except FamilyFinancialIncomeAllocationError as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": str(exc)}, headers={"Cache-Control": "no-store"}) from exc
        return runtime.JSONResponse(result, headers={"Cache-Control": "no-store"})

    @router.post("/api/dividends/financial-income-personal-comprehensive-tax")
    async def financial_income_personal_comprehensive_tax(request: Request) -> JSONResponse:
        """Compare explicit tax-base scenarios using the 2026 national basic rates."""
        runtime.get_current_username(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "PERSONAL_COMPREHENSIVE_TAX_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            ) from exc

        required_fields = {
            "tax_base_before_financial_income_krw",
            "financial_income_gross_krw",
            "assumed_financial_income_included_in_tax_base_krw",
        }
        if not isinstance(body, dict) or set(body) != required_fields:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "PERSONAL_COMPREHENSIVE_TAX_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

        from app.services.tax import (
            PersonalComprehensiveTaxError,
            calculate_personal_comprehensive_tax_basic_rate_2026,
        )

        try:
            result = calculate_personal_comprehensive_tax_basic_rate_2026(**body)
        except PersonalComprehensiveTaxError as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": str(exc)},
                headers={"Cache-Control": "no-store"},
            ) from exc
        return runtime.JSONResponse(result, headers={"Cache-Control": "no-store"})

    @router.post("/api/dividends/financial-income-article62-comparison")
    async def financial_income_article62_comparison(request: Request) -> JSONResponse:
        """Return a stateless Article 62 comparison before credits."""
        runtime.get_current_username(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": "ARTICLE62_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"}) from exc
        from app.services.tax import PersonalComprehensiveTaxError, calculate_financial_income_article62_comparison_2026
        try:
            result = calculate_financial_income_article62_comparison_2026(**body) if isinstance(body, dict) else None
        except PersonalComprehensiveTaxError as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": str(exc)}, headers={"Cache-Control": "no-store"}) from exc
        if result is None:
            raise runtime.HTTPException(status_code=400, detail={"code": "ARTICLE62_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"})
        return runtime.JSONResponse(result, headers={"Cache-Control": "no-store"})

    @router.post("/api/dividends/financial-income-simulation")
    async def simulate_financial_income(request: Request) -> JSONResponse:
        """Return a stateless annual financial-income screening projection."""
        username = runtime.get_current_username(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            ) from exc
        if not isinstance(body, dict):
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

        allowed_fields = {
            "owner",
            "expected_remaining_interest_gross_krw",
            "current_month_remaining_dividend_gross_krw",
        }
        if set(body) - allowed_fields:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

        owner = body.get("owner", "모두")
        if not isinstance(owner, str) or not owner.strip():
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_OWNER_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

        from app.services.tax import (
            FinancialIncomeProjectionError,
            get_financial_income_projection_for_user,
        )

        try:
            result = await get_financial_income_projection_for_user(
                username,
                owner=owner.strip(),
                expected_remaining_interest_gross_krw=body.get(
                    "expected_remaining_interest_gross_krw", 0.0
                ),
                current_month_remaining_dividend_gross_krw=body.get(
                    "current_month_remaining_dividend_gross_krw", 0.0
                ),
            )
        except FinancialIncomeProjectionError as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": str(exc)},
                headers={"Cache-Control": "no-store"},
            ) from exc

        return runtime.JSONResponse(result, headers={"Cache-Control": "no-store"})

    @router.post("/api/dividends/financial-income-what-if")
    async def simulate_financial_income_what_if(request: Request) -> JSONResponse:
        """Return a stateless financial-income and investment-method What-if."""
        username = runtime.get_current_username(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            ) from exc
        if not isinstance(body, dict):
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

        allowed_fields = {
            "owner",
            "as_of",
            "expected_remaining_interest_gross_krw",
            "current_month_remaining_dividend_gross_krw",
            "additional_dividend_gross_krw",
            "additional_interest_gross_krw",
            "additional_foreign_share_realized_gain_krw",
            "additional_kr_listed_overseas_etf_taxable_gain_krw",
            "high_dividend_scenario",
            "investment_scenario",
        }
        if set(body) - allowed_fields:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

        owner = body.get("owner", "모두")
        if not isinstance(owner, str) or not owner.strip():
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_OWNER_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

        high_dividend_scenario = body.get("high_dividend_scenario")
        if high_dividend_scenario is not None:
            if not isinstance(high_dividend_scenario, dict):
                raise runtime.HTTPException(
                    status_code=400,
                    detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                    headers={"Cache-Control": "no-store"},
                )
            allowed_high_dividend_fields = {
                "special_dividend_income_krw",
                "high_dividend_company_confirmed",
                "separate_taxation_requested",
            }
            if set(high_dividend_scenario) - allowed_high_dividend_fields:
                raise runtime.HTTPException(
                    status_code=400,
                    detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                    headers={"Cache-Control": "no-store"},
                )

        investment_scenario = body.get("investment_scenario")
        if investment_scenario is not None:
            if not isinstance(investment_scenario, dict):
                raise runtime.HTTPException(
                    status_code=400,
                    detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                    headers={"Cache-Control": "no-store"},
                )
            allowed_investment_fields = {
                "asset_type",
                "annual_distribution_krw",
                "annual_realized_gain_krw",
                "taxable_etf_gain_krw",
                "existing_corporate_taxable_income_krw",
                "corporate_deductible_expenses_krw",
                "corporation_to_owner_distribution_krw",
                "domestic_dividend_exclusion_eligible",
                "domestic_dividend_ownership_pct",
                "domestic_dividend_holding_months",
                "us_treaty_parent_rate_qualified",
                "foreign_subsidiary_exclusion_qualified",
                "foreign_ownership_pct",
            }
            if set(investment_scenario) - allowed_investment_fields:
                raise runtime.HTTPException(
                    status_code=400,
                    detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                    headers={"Cache-Control": "no-store"},
                )
            asset_type = investment_scenario.get("asset_type")
            if not isinstance(asset_type, str) or not asset_type.strip():
                raise runtime.HTTPException(
                    status_code=400,
                    detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                    headers={"Cache-Control": "no-store"},
                )

        from app.services.tax import (
            FinancialIncomeProjectionError,
            FinancialIncomeWhatIfError,
            HighDividendSpecialTaxError,
            InvestmentTaxComparisonError,
            get_financial_income_what_if_for_user,
        )

        try:
            result = await get_financial_income_what_if_for_user(
                username,
                owner=owner.strip(),
                **({"as_of": body["as_of"]} if "as_of" in body else {}),
                expected_remaining_interest_gross_krw=body.get(
                    "expected_remaining_interest_gross_krw", 0.0
                ),
                current_month_remaining_dividend_gross_krw=body.get(
                    "current_month_remaining_dividend_gross_krw", 0.0
                ),
                additional_dividend_gross_krw=body.get(
                    "additional_dividend_gross_krw", 0.0
                ),
                additional_interest_gross_krw=body.get(
                    "additional_interest_gross_krw", 0.0
                ),
                investment_scenario=investment_scenario,
                **(
                    {
                        "additional_foreign_share_realized_gain_krw": body.get(
                            "additional_foreign_share_realized_gain_krw"
                        )
                    }
                    if "additional_foreign_share_realized_gain_krw" in body
                    else {}
                ),
                **(
                    {
                        "additional_kr_listed_overseas_etf_taxable_gain_krw": body.get(
                            "additional_kr_listed_overseas_etf_taxable_gain_krw"
                        )
                    }
                    if "additional_kr_listed_overseas_etf_taxable_gain_krw" in body
                    else {}
                ),
                **(
                    {"high_dividend_scenario": high_dividend_scenario}
                    if high_dividend_scenario is not None
                    else {}
                ),
            )
        except (
            FinancialIncomeProjectionError,
            FinancialIncomeWhatIfError,
            HighDividendSpecialTaxError,
            InvestmentTaxComparisonError,
        ) as exc:
            raise runtime.HTTPException(
                status_code=400,
                detail={"code": str(exc)},
                headers={"Cache-Control": "no-store"},
            ) from exc

        return runtime.JSONResponse(result, headers={"Cache-Control": "no-store"})

    return router
