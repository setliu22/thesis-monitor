from decimal import Decimal
from sqlalchemy import select
from app.models import RuleVersion, Observation, Alert
from app.rules import evaluate_rule, evaluate_company


def test_rule_boundaries_and_unavailable():
    rule=RuleVersion(metric='revenue_growth',operator='lt',threshold=Decimal('5'))
    assert evaluate_rule(rule,{'value':'4'})
    assert not evaluate_rule(rule,{'value':'5'})
    assert not evaluate_rule(rule,{'value':None})
    for op,expected in [('lte',True),('gt',False),('gte',True)]:
        rule.operator=op; assert evaluate_rule(rule,{'value':'5'})==expected


def test_alerts_are_versioned_idempotent_and_ignore_old_observations(sessions):
    with sessions() as s:
        s.add(RuleVersion(company_id=1,group_key='r',version=1,name='Growth',metric='revenue_growth',operator='lt',threshold=5,enabled=True,period_kind='quarter'))
        s.add(Observation(company_id=1,identity='old',metric='revenue_growth',period_end='2025-03-31',kind='quarter',value=1,unit='%',active=False,payload={'value':'1'}))
        s.add(Observation(company_id=1,identity='new',metric='revenue_growth',period_end='2025-06-30',kind='quarter',value=4,unit='%',active=True,payload={'value':'4','end':'2025-06-30','kind':'quarter','sources':[]}))
        s.commit()
        assert evaluate_company(s,1)==1; s.commit()
        assert evaluate_company(s,1)==0
        s.add(RuleVersion(company_id=1,group_key='r',version=2,name='Growth edited',metric='revenue_growth',operator='lt',threshold=6,enabled=True,period_kind='quarter')); s.commit()
        assert evaluate_company(s,1)==1; s.commit()
        assert len(list(s.scalars(select(Alert))))==2
