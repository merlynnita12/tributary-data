"""
Tributary synthetic fincrime dataset generator.

Generates five CSV files representing a fictional European PSP serving SMBs:
- customers.csv      (50k SMB customers across 12 EU countries)
- transactions.csv   (5m transactions over 18 months)
- chargebacks.csv    (~5k chargebacks linked to transactions)
- kyc_events.csv     (~150k KYC onboarding and review events)
- compliance_alerts.csv (~25k alerts with true/false positive labels)

Designed for:
- SQL analysis practice (joins, windows, aggregations, cohorts)
- dbt staging/intermediate/mart modeling
- A/B testing simulation on fraud rule changes
- DecisionLens demo case

Fraud patterns embedded:
- Card testing (small repeated transactions before larger ones)
- Account takeover (sudden geography or device shifts)
- Money muling (structured inflow/outflow patterns)
- Sanctions exposure (transactions touching synthetic sanctioned entities)
- First-party fraud (chargebacks on legitimate transactions)

All data is synthetic. No real customer data, no real sanctions entities,
no real merchant identifiers. The script is deterministic via seed.

Usage:
    python generate.py [--output-dir DIR] [--seed N]

Defaults to ./output and seed=42.
"""

import argparse
import csv
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

# ---- Configuration ----
N_CUSTOMERS = 50_000
N_TRANSACTIONS = 5_000_000
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2025, 6, 30)
TOTAL_DAYS = (END_DATE - START_DATE).days

# EU country mix (weighted toward NL, DE, FR, ES, IT for realism)
COUNTRIES = {
    'NL': 0.18, 'DE': 0.16, 'FR': 0.14, 'ES': 0.11, 'IT': 0.10,
    'BE': 0.07, 'PT': 0.06, 'IE': 0.05, 'AT': 0.05, 'PL': 0.04,
    'SE': 0.02, 'DK': 0.02,
}

# Industry mix for SMBs
INDUSTRIES = [
    'retail_online', 'retail_physical', 'restaurants_food', 'professional_services',
    'wholesale_b2b', 'travel_hospitality', 'health_wellness', 'creative_media',
    'construction_trades', 'tech_software', 'beauty_personal_care', 'logistics',
]

# Merchant category codes (simplified MCC-like)
MCCS = {
    'retail_online': ['5411', '5912', '5942', '5969', '5732'],
    'retail_physical': ['5411', '5651', '5712', '5942', '5947'],
    'restaurants_food': ['5812', '5813', '5814'],
    'professional_services': ['7392', '8931', '7361'],
    'wholesale_b2b': ['5039', '5044', '5065'],
    'travel_hospitality': ['3000', '3500', '4111', '4511', '7011'],
    'health_wellness': ['5912', '8011', '8021', '8050'],
    'creative_media': ['5970', '7333', '7929'],
    'construction_trades': ['1520', '1711', '1731', '1750'],
    'tech_software': ['5734', '5045', '7372'],
    'beauty_personal_care': ['5977', '7230', '7298'],
    'logistics': ['4214', '4215', '4225'],
}

TRANSACTION_TYPES = {
    'card_payment': 0.62,
    'sepa_transfer': 0.22,
    'refund': 0.09,
    'sepa_instant': 0.07,
}

CURRENCIES_BY_COUNTRY = {
    'NL': 'EUR', 'DE': 'EUR', 'FR': 'EUR', 'ES': 'EUR', 'IT': 'EUR',
    'BE': 'EUR', 'PT': 'EUR', 'IE': 'EUR', 'AT': 'EUR',
    'PL': 'PLN', 'SE': 'SEK', 'DK': 'DKK',
}

CHARGEBACK_REASONS = [
    'fraudulent_transaction', 'product_not_received', 'product_not_as_described',
    'duplicate_charge', 'cancelled_recurring', 'credit_not_processed',
    'authorization_error', 'first_party_fraud',
]

KYC_EVENT_TYPES = [
    'initial_onboarding', 'periodic_review', 'enhanced_due_diligence',
    'risk_reclassification', 'pep_screening', 'sanctions_screening',
]

ALERT_TYPES = [
    'high_velocity_transactions', 'unusual_geography', 'structuring_pattern',
    'sanctions_potential_match', 'high_risk_merchant', 'sudden_volume_spike',
    'round_amount_pattern', 'card_testing_pattern', 'mule_indicator',
]


def weighted_choice(d, rng):
    """Pick a key from dict d with values as weights."""
    keys = list(d.keys())
    weights = list(d.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def generate_customers(rng):
    """Generate the customers table."""
    print(f"Generating {N_CUSTOMERS:,} customers...")
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        country = weighted_choice(COUNTRIES, rng)
        industry = rng.choice(INDUSTRIES)
        # Signup date weighted slightly toward earlier in the window
        signup_days_ago = int(rng.triangular(0, TOTAL_DAYS, TOTAL_DAYS * 0.6))
        signup_date = START_DATE + timedelta(days=signup_days_ago)
        # Customer lifecycle stage
        days_active = (END_DATE - signup_date).days
        if days_active < 30:
            stage = 'new'
        elif days_active < 180:
            stage = 'growing'
        elif days_active < 365:
            stage = 'established'
        else:
            stage = 'mature'
        # Risk score baseline (most low, some medium, few high)
        risk_score = max(0, min(100, int(rng.gauss(25, 15))))
        # Initial risk classification
        if risk_score < 30:
            risk_class = 'low'
        elif risk_score < 60:
            risk_class = 'medium'
        else:
            risk_class = 'high'
        # A small fraction become "bad actors" for embedded patterns
        is_bad_actor = rng.random() < 0.008  # ~400 of 50k
        # Activity level (transactions per day average)
        activity_base = {
            'new': 0.5, 'growing': 2.0, 'established': 4.5, 'mature': 6.0,
        }[stage]
        daily_tx_rate = max(0.1, rng.gauss(activity_base, activity_base * 0.5))

        customers.append({
            'customer_id': f'CUST_{i:06d}',
            'country': country,
            'industry': industry,
            'signup_date': signup_date.strftime('%Y-%m-%d'),
            'lifecycle_stage': stage,
            'initial_risk_score': risk_score,
            'initial_risk_class': risk_class,
            'is_bad_actor': is_bad_actor,
            'daily_tx_rate': round(daily_tx_rate, 2),
        })
    return customers


def generate_transactions(customers, rng):
    """Generate transactions. Returns list of dicts."""
    print(f"Generating ~{N_TRANSACTIONS:,} transactions (this takes a moment)...")
    transactions = []
    tx_id = 1

    # Pre-compute customer signup datetimes
    customer_lookup = {
        c['customer_id']: {
            'signup': datetime.strptime(c['signup_date'], '%Y-%m-%d'),
            'country': c['country'],
            'industry': c['industry'],
            'daily_rate': c['daily_tx_rate'],
            'is_bad_actor': c['is_bad_actor'],
        }
        for c in customers
    }

    # Compute scale factor so we hit the target transaction count
    # spread across all customers rather than truncating later ones
    total_expected = sum(
        info['daily_rate'] * max(1, (END_DATE - info['signup']).days)
        for info in customer_lookup.values()
    )
    scale = N_TRANSACTIONS / total_expected if total_expected > 0 else 1.0

    # Build per-customer transaction counts based on daily rate * days active
    for cust_id, info in customer_lookup.items():
        days_active = (END_DATE - info['signup']).days
        if days_active < 1:
            continue
        expected_count = int(info['daily_rate'] * days_active * scale)
        # Add poisson-ish noise
        actual_count = max(1, int(rng.gauss(expected_count, max(1, expected_count * 0.2))))

        country = info['country']
        currency = CURRENCIES_BY_COUNTRY[country]
        mcc_options = MCCS[info['industry']]

        for _ in range(actual_count):
            # Random datetime in customer's active window
            days_offset = rng.randint(0, days_active - 1) if days_active > 1 else 0
            tx_date = info['signup'] + timedelta(
                days=days_offset,
                hours=rng.randint(0, 23),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            if tx_date > END_DATE:
                continue

            tx_type = weighted_choice(TRANSACTION_TYPES, rng)

            # Amount distribution depends on type and industry
            if tx_type == 'refund':
                amount = -round(rng.lognormvariate(3.0, 1.0), 2)
            elif tx_type == 'sepa_transfer':
                amount = round(rng.lognormvariate(5.5, 1.5), 2)
            elif tx_type == 'sepa_instant':
                amount = round(rng.lognormvariate(4.5, 1.2), 2)
            else:  # card_payment
                amount = round(rng.lognormvariate(3.5, 1.3), 2)

            # Status mostly 'completed', some 'failed' or 'pending'
            status_roll = rng.random()
            if status_roll < 0.94:
                status = 'completed'
            elif status_roll < 0.98:
                status = 'failed'
            else:
                status = 'pending'

            # Counterparty country (mostly same as customer, some cross-border)
            if rng.random() < 0.85:
                counterparty_country = country
            else:
                counterparty_country = weighted_choice(COUNTRIES, rng)

            transactions.append({
                'transaction_id': f'TXN_{tx_id:09d}',
                'customer_id': cust_id,
                'timestamp': tx_date.strftime('%Y-%m-%d %H:%M:%S'),
                'amount': amount,
                'currency': currency,
                'type': tx_type,
                'status': status,
                'mcc': rng.choice(mcc_options),
                'counterparty_country': counterparty_country,
                'is_cross_border': counterparty_country != country,
            })
            tx_id += 1

    return transactions


def inject_fraud_patterns(transactions, customers, rng):
    """Inject specific fraud patterns for bad-actor customers."""
    print("Injecting fraud patterns into bad actor accounts...")
    bad_actors = [c['customer_id'] for c in customers if c['is_bad_actor']]
    print(f"  {len(bad_actors)} bad actor accounts")

    # Index transactions by customer
    tx_by_customer = {}
    for tx in transactions:
        tx_by_customer.setdefault(tx['customer_id'], []).append(tx)

    pattern_log = []  # for ground truth tracking

    # Assign patterns to bad actors
    patterns = ['card_testing', 'account_takeover', 'money_muling',
                'sanctions_exposure', 'first_party_fraud']

    for cust_id in bad_actors:
        if cust_id not in tx_by_customer:
            continue
        pattern = rng.choice(patterns)
        cust_txs = tx_by_customer[cust_id]
        if not cust_txs:
            continue

        if pattern == 'card_testing':
            # Add 10-20 small transactions in a tight time window before a large one
            base_time = datetime.strptime(cust_txs[0]['timestamp'], '%Y-%m-%d %H:%M:%S')
            for j in range(rng.randint(10, 20)):
                cust_txs.append({
                    **cust_txs[0],
                    'transaction_id': f'TXN_INJ_{cust_id}_{j:03d}_CT',
                    'timestamp': (base_time + timedelta(minutes=j*2)).strftime('%Y-%m-%d %H:%M:%S'),
                    'amount': round(rng.uniform(0.5, 5.0), 2),
                })
            pattern_log.append((cust_id, pattern))

        elif pattern == 'account_takeover':
            # A subset of transactions suddenly from a different country
            n_ato = min(len(cust_txs), rng.randint(5, 15))
            ato_country = rng.choice([c for c in COUNTRIES if c != cust_txs[0]['counterparty_country']])
            for tx in rng.sample(cust_txs, n_ato):
                tx['counterparty_country'] = ato_country
                tx['is_cross_border'] = True
            pattern_log.append((cust_id, pattern))

        elif pattern == 'money_muling':
            # Structured pattern: large inflow followed by multiple outflows
            base_time = datetime.strptime(cust_txs[0]['timestamp'], '%Y-%m-%d %H:%M:%S')
            inflow_amount = round(rng.uniform(9000, 9900), 2)  # just under reporting threshold
            cust_txs.append({
                'transaction_id': f'TXN_INJ_{cust_id}_INFLOW_MM',
                'customer_id': cust_id,
                'timestamp': base_time.strftime('%Y-%m-%d %H:%M:%S'),
                'amount': inflow_amount,
                'currency': cust_txs[0]['currency'],
                'type': 'sepa_transfer',
                'status': 'completed',
                'mcc': '0000',
                'counterparty_country': rng.choice(list(COUNTRIES.keys())),
                'is_cross_border': True,
            })
            # Multiple smaller outflows
            for j in range(rng.randint(3, 8)):
                cust_txs.append({
                    'transaction_id': f'TXN_INJ_{cust_id}_OUT_{j:02d}_MM',
                    'customer_id': cust_id,
                    'timestamp': (base_time + timedelta(hours=j+1)).strftime('%Y-%m-%d %H:%M:%S'),
                    'amount': round(inflow_amount / rng.randint(4, 8), 2),
                    'currency': cust_txs[0]['currency'],
                    'type': 'sepa_instant',
                    'status': 'completed',
                    'mcc': '0000',
                    'counterparty_country': rng.choice(list(COUNTRIES.keys())),
                    'is_cross_border': True,
                })
            pattern_log.append((cust_id, pattern))

        elif pattern == 'sanctions_exposure':
            # A couple of transactions to a synthetic sanctioned counterparty
            for j in range(rng.randint(1, 3)):
                if cust_txs:
                    tx = rng.choice(cust_txs)
                    tx['counterparty_country'] = 'XX'  # synthetic sanctioned country code
                    tx['is_cross_border'] = True
            pattern_log.append((cust_id, pattern))

        elif pattern == 'first_party_fraud':
            # Marked for chargebacking later — handled in chargeback generation
            pattern_log.append((cust_id, pattern))

    # Flatten back into transactions list
    transactions[:] = []
    for txs in tx_by_customer.values():
        transactions.extend(txs)

    return pattern_log


def generate_chargebacks(transactions, pattern_log, rng):
    """Generate chargebacks. Some legitimate, some first-party fraud."""
    print("Generating chargebacks...")
    chargebacks = []
    cb_id = 1

    # Get first-party fraud customers
    fpf_customers = {c for c, p in pattern_log if p == 'first_party_fraud'}

    # Eligible transactions: card payments, completed
    eligible = [t for t in transactions
                if t['type'] == 'card_payment' and t['status'] == 'completed']

    # Base chargeback rate ~0.08% for legitimate disputes
    n_legitimate = int(len(eligible) * 0.0008)
    legitimate_sample = rng.sample(eligible, min(n_legitimate, len(eligible)))

    for tx in legitimate_sample:
        tx_date = datetime.strptime(tx['timestamp'], '%Y-%m-%d %H:%M:%S')
        cb_date = tx_date + timedelta(days=rng.randint(5, 90))
        if cb_date > END_DATE:
            continue
        reason = rng.choice([r for r in CHARGEBACK_REASONS if r != 'first_party_fraud'])
        chargebacks.append({
            'chargeback_id': f'CB_{cb_id:06d}',
            'transaction_id': tx['transaction_id'],
            'customer_id': tx['customer_id'],
            'chargeback_date': cb_date.strftime('%Y-%m-%d'),
            'reason': reason,
            'amount': tx['amount'],
            'is_first_party_fraud': False,
        })
        cb_id += 1

    # First-party fraud chargebacks (higher rate for these customers)
    for cust_id in fpf_customers:
        cust_txs = [t for t in eligible if t['customer_id'] == cust_id]
        if not cust_txs:
            continue
        n_fpf = min(len(cust_txs), rng.randint(3, 8))
        for tx in rng.sample(cust_txs, n_fpf):
            tx_date = datetime.strptime(tx['timestamp'], '%Y-%m-%d %H:%M:%S')
            cb_date = tx_date + timedelta(days=rng.randint(30, 60))
            if cb_date > END_DATE:
                continue
            chargebacks.append({
                'chargeback_id': f'CB_{cb_id:06d}',
                'transaction_id': tx['transaction_id'],
                'customer_id': cust_id,
                'chargeback_date': cb_date.strftime('%Y-%m-%d'),
                'reason': 'first_party_fraud',
                'amount': tx['amount'],
                'is_first_party_fraud': True,
            })
            cb_id += 1

    return chargebacks


def generate_kyc_events(customers, rng):
    """Generate KYC events."""
    print("Generating KYC events...")
    events = []
    ev_id = 1

    for c in customers:
        signup = datetime.strptime(c['signup_date'], '%Y-%m-%d')

        # Initial onboarding (everyone)
        events.append({
            'event_id': f'KYC_{ev_id:07d}',
            'customer_id': c['customer_id'],
            'event_date': signup.strftime('%Y-%m-%d'),
            'event_type': 'initial_onboarding',
            'risk_score_at_event': c['initial_risk_score'],
            'outcome': 'passed' if c['initial_risk_score'] < 70 else 'enhanced_review',
        })
        ev_id += 1

        # Sanctions screening at onboarding (everyone)
        events.append({
            'event_id': f'KYC_{ev_id:07d}',
            'customer_id': c['customer_id'],
            'event_date': signup.strftime('%Y-%m-%d'),
            'event_type': 'sanctions_screening',
            'risk_score_at_event': c['initial_risk_score'],
            'outcome': 'clear' if not c['is_bad_actor'] else rng.choice(['clear', 'clear', 'potential_match']),
        })
        ev_id += 1

        # Periodic reviews (annual for low risk, more frequent for higher)
        days_active = (END_DATE - signup).days
        if c['initial_risk_class'] == 'low':
            review_interval = 365
        elif c['initial_risk_class'] == 'medium':
            review_interval = 180
        else:
            review_interval = 90

        n_reviews = days_active // review_interval
        for i in range(1, n_reviews + 1):
            review_date = signup + timedelta(days=i * review_interval)
            if review_date > END_DATE:
                break
            # Risk score can drift
            score_drift = rng.gauss(0, 5)
            new_score = max(0, min(100, c['initial_risk_score'] + score_drift * i))
            events.append({
                'event_id': f'KYC_{ev_id:07d}',
                'customer_id': c['customer_id'],
                'event_date': review_date.strftime('%Y-%m-%d'),
                'event_type': 'periodic_review',
                'risk_score_at_event': int(new_score),
                'outcome': 'passed' if new_score < 70 else 'enhanced_review',
            })
            ev_id += 1

    return events


def generate_compliance_alerts(transactions, customers, pattern_log, rng):
    """Generate alerts. Bad actors get more true positives, others get false positives."""
    print("Generating compliance alerts...")
    alerts = []
    alert_id = 1

    bad_actor_set = {c for c, p in pattern_log}
    pattern_lookup = dict(pattern_log)

    # Group txs by customer for context
    tx_by_customer = {}
    for tx in transactions:
        tx_by_customer.setdefault(tx['customer_id'], []).append(tx)

    # Generate alerts for bad actors (true positives, mostly)
    for cust_id in bad_actor_set:
        cust_txs = tx_by_customer.get(cust_id, [])
        if not cust_txs:
            continue
        pattern = pattern_lookup[cust_id]
        # Map pattern to plausible alert types
        alert_type_map = {
            'card_testing': 'card_testing_pattern',
            'account_takeover': 'unusual_geography',
            'money_muling': 'mule_indicator',
            'sanctions_exposure': 'sanctions_potential_match',
            'first_party_fraud': 'sudden_volume_spike',
        }
        alert_type = alert_type_map[pattern]
        n_alerts = rng.randint(1, 4)
        for _ in range(n_alerts):
            tx = rng.choice(cust_txs)
            alerts.append({
                'alert_id': f'ALERT_{alert_id:07d}',
                'customer_id': cust_id,
                'related_transaction_id': tx['transaction_id'],
                'alert_date': tx['timestamp'][:10],
                'alert_type': alert_type,
                'severity': rng.choice(['medium', 'high', 'high', 'critical']),
                'is_true_positive': True,
                'analyst_disposition': rng.choice(['confirmed_fraud', 'sar_filed', 'escalated']),
            })
            alert_id += 1

    # Generate false positive alerts on non-bad-actor customers
    non_bad = [c['customer_id'] for c in customers if c['customer_id'] not in bad_actor_set]
    n_false_positives = int(len(non_bad) * 0.4)  # 40% of clean customers get a false alert at some point
    fp_sample = rng.sample(non_bad, min(n_false_positives, len(non_bad)))

    for cust_id in fp_sample:
        cust_txs = tx_by_customer.get(cust_id, [])
        if not cust_txs:
            continue
        n_alerts = rng.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]
        for _ in range(n_alerts):
            tx = rng.choice(cust_txs)
            alerts.append({
                'alert_id': f'ALERT_{alert_id:07d}',
                'customer_id': cust_id,
                'related_transaction_id': tx['transaction_id'],
                'alert_date': tx['timestamp'][:10],
                'alert_type': rng.choice(ALERT_TYPES),
                'severity': rng.choice(['low', 'low', 'medium', 'medium', 'high']),
                'is_true_positive': False,
                'analyst_disposition': rng.choice(['cleared', 'cleared', 'cleared', 'monitor']),
            })
            alert_id += 1

    return alerts


def write_csv(rows, path, fieldnames):
    """Write a list of dicts to a CSV file."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='./output')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)

    print(f"Tributary synthetic data generator")
    print(f"Seed: {args.seed}, output: {out_dir.resolve()}")
    print()

    # Generate
    customers = generate_customers(rng)
    transactions = generate_transactions(customers, rng)
    pattern_log = inject_fraud_patterns(transactions, customers, rng)
    chargebacks = generate_chargebacks(transactions, pattern_log, rng)
    kyc_events = generate_kyc_events(customers, rng)
    alerts = generate_compliance_alerts(transactions, customers, pattern_log, rng)

    # Write
    print()
    print("Writing CSVs...")
    write_csv(customers, out_dir / 'customers.csv', list(customers[0].keys()))
    print(f"  customers.csv         {len(customers):>10,} rows")

    write_csv(transactions, out_dir / 'transactions.csv', list(transactions[0].keys()))
    print(f"  transactions.csv      {len(transactions):>10,} rows")

    write_csv(chargebacks, out_dir / 'chargebacks.csv', list(chargebacks[0].keys()))
    print(f"  chargebacks.csv       {len(chargebacks):>10,} rows")

    write_csv(kyc_events, out_dir / 'kyc_events.csv', list(kyc_events[0].keys()))
    print(f"  kyc_events.csv        {len(kyc_events):>10,} rows")

    write_csv(alerts, out_dir / 'compliance_alerts.csv', list(alerts[0].keys()))
    print(f"  compliance_alerts.csv {len(alerts):>10,} rows")

    # Write the ground truth pattern log
    with open(out_dir / 'ground_truth_patterns.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['customer_id', 'embedded_pattern'])
        writer.writerows(pattern_log)
    print(f"  ground_truth_patterns.csv {len(pattern_log):>6,} rows  (do not include in analysis - this is the answer key)")

    print()
    print("Done.")


if __name__ == '__main__':
    main()
