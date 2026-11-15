from datetime import datetime, timezone
from decimal import Decimal
from app.financials import normalize

# All values in this module are intentionally synthetic test inputs.
def fact(val, start, end, filed='2025-08-01', accn='a', **kw):
    return dict(val=val, start=start, end=end, filed=filed, accn=accn, form='10-K', **kw)

def payload(**tags):
    return {'facts': {'us-gaap': {tag: {'units': {'USD': values}} for tag, values in tags.items()}}}

def get(data, metric, end, kind='annual', as_of='2026-01-01'):
    results = normalize(data, datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc))
    return next(x for x in results if x['metric']==metric and x['end']==end and x['kind']==kind)

def test_growth_and_margin_use_matching_fiscal_durations():
    data=payload(RevenueFromContractWithCustomerExcludingAssessedTax=[fact(100,'2023-07-01','2024-06-30'),fact(120,'2024-07-01','2025-06-30')],OperatingIncomeLoss=[fact(12,'2024-07-01','2025-06-30')])
    assert Decimal(get(data,'revenue_growth','2025-06-30')['value']) == 20
    assert Decimal(get(data,'operating_margin','2025-06-30')['value']) == 10

def test_ytd_cash_flow_is_derived_into_discrete_quarters():
    data=payload(NetCashProvidedByUsedInOperatingActivities=[fact(190,'2024-07-01','2024-12-31'),fact(300,'2024-07-01','2025-03-31')])
    o=get(data,'operating_cash_flow','2025-03-31','quarter')
    assert Decimal(o['value']) == 110
    assert o['start']=='2025-01-01' and o['derivation']=='ytd_difference'
    assert len(o['sources'])==2

def test_different_year_or_tag_does_not_derive_a_quarter():
    data=payload(Revenues=[fact(190,'2023-07-01','2023-12-31')],RevenueFromContractWithCustomerExcludingAssessedTax=[fact(300,'2024-07-01','2025-03-31')])
    assert not [x for x in normalize(data) if x['metric']=='revenue' and x['kind']=='quarter']

def test_zero_or_negative_growth_denominator_is_unavailable():
    for prior in [0,-20]:
        data=payload(Revenues=[fact(prior,'2023-07-01','2024-06-30'),fact(120,'2024-07-01','2025-06-30')])
        o=get(data,'revenue_growth','2025-06-30')
        assert o['value'] is None and o['unavailable_reason']

def test_amendments_respect_as_of_date():
    data=payload(Revenues=[fact(100,'2024-07-01','2025-06-30',filed='2025-08-01'),fact(110,'2024-07-01','2025-06-30',filed='2025-09-01',accn='b')])
    assert get(data,'revenue','2025-06-30',as_of='2025-08-15')['value']=='100'
    assert get(data,'revenue','2025-06-30',as_of='2025-10-01')['value']=='110'

def test_no_silent_growth_across_tag_changes():
    data=payload(Revenues=[fact(100,'2023-07-01','2024-06-30')],SalesRevenueNet=[fact(110,'2024-07-01','2025-06-30')])
    assert get(data,'revenue_growth','2025-06-30')['value'] is None

def test_instant_debt_and_fcf():
    data=payload(LongTermDebtCurrent=[dict(val=20,end='2025-06-30',filed='2025-08-01',accn='a',form='10-K')],LongTermDebtNoncurrent=[dict(val=80,end='2025-06-30',filed='2025-08-01',accn='a',form='10-K')],NetCashProvidedByUsedInOperatingActivities=[fact(100,'2024-07-01','2025-06-30')],PaymentsToAcquirePropertyPlantAndEquipment=[fact(30,'2024-07-01','2025-06-30')])
    assert get(data,'debt','2025-06-30','instant')['value']=='100'
    assert get(data,'free_cash_flow','2025-06-30')['value']=='70'

def test_missing_same_period_income_does_not_create_margin():
    data=payload(Revenues=[fact(100,'2024-07-01','2025-06-30')],OperatingIncomeLoss=[fact(20,'2023-07-01','2024-06-30')])
    assert get(data,'operating_margin','2025-06-30')['value'] is None
