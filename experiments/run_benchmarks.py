"""Repeated-trial benchmark runner.

Loads validated benchmark configurations, expands policy/video/repeat
combinations into trials, and produces a reproducible randomized trial order.
"""

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import random
import uuid


@dataclass(frozen=True)
class Trial:
    run_id: str
    policy: str
    source_id: str
    repeat_index: int


def build_trials(benchmark_id, policies, sources, repeats):
    """Expand policies, sources, and repeats into individual benchmark trials."""
    trials = []

    for policy in policies:
        for source_id in sources:
            for repeat_index in range(1, repeats + 1):
                trials.append(
                    Trial(
                        run_id=uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{benchmark_id}:{policy}:{source_id}:{repeat_index}",
                        ).hex,
                        policy=policy,
                        source_id=source_id,
                        repeat_index=repeat_index,
                    )
                )

    return trials

def randomize_trials(trials, seed):
    """Return trials in a reproducible randomized order."""
    randomized = list(trials)
    rng = random.Random(seed)
    rng.shuffle(randomized)
    return randomized


def load_config(path):
    """Load a benchmark configuration from a JSON file."""
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Benchmark configuration not found: {config_path}"
        )

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    required_fields = ["benchmark_id", "policies", "sources", "repeats"]

    missing_fields = [
        field for field in required_fields
        if field not in config
    ]

    if missing_fields:
        raise ValueError(
            "Benchmark configuration is missing required fields: "
            + ", ".join(missing_fields)
        )

    return config

def build_plan(config, seed):
    """Build and randomize the complete benchmark trial plan."""
    trials = build_trials(
        benchmark_id=config["benchmark_id"],
        policies=config["policies"],
        sources=config["sources"],
        repeats=config["repeats"],
    )

    randomized_trials = randomize_trials(trials, seed)

    return {
        "benchmark_id": config["benchmark_id"],
        "seed": seed,
        "trial_count": len(randomized_trials),
        "trials": [
            {
                "trial_index": index,
                "run_id": trial.run_id,
                "policy": trial.policy,
                "source_id": trial.source_id,
                "repeat_index": trial.repeat_index,
            }
            for index, trial in enumerate(randomized_trials, start=1)
        ],
    }

def save_plan(plan, output_path):
    """Save a benchmark plan without overwriting an existing plan."""
    output_path = Path(output_path)

    if output_path.exists():
        raise FileExistsError(
            f"Benchmark plan already exists: {output_path}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(plan, file, indent=2)

    return output_path


def main():
    """Generate and save a benchmark trial plan."""
    parser = argparse.ArgumentParser(
        description="Generate a reproducible randomized benchmark plan."
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to the benchmark JSON configuration.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=6411,
        help="Random seed used to order trials.",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path where plan.json will be written.",
    )

    args = parser.parse_args()

    config = load_config(args.config)
    plan = build_plan(config, args.seed)
    output_path = save_plan(plan, args.output)

    print(f"Benchmark: {plan['benchmark_id']}")
    print(f"Seed: {plan['seed']}")
    print(f"Trials: {plan['trial_count']}")
    print(f"Plan saved to: {output_path}")


if __name__ == "__main__":
    main()
