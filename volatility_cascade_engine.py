from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import networkx as nx


SEED = 42
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class Fund:
    name: str
    equity: float
    leverage: float
    margin_threshold: float
    liquidation_fraction: float
    exposures: Dict[str, float] = field(default_factory=dict)

    @property
    def asset_gross(self) -> float:
        return sum(self.exposures.values())

    @property
    def debt(self) -> float:
        return max(self.asset_gross - self.equity, 0.0)

    def equity_after_prices(self, prices: Dict[str, float], initial_prices: Dict[str, float]) -> float:
        asset_value = 0.0
        for asset, notional in self.exposures.items():
            scaled_value = notional * prices[asset] / initial_prices[asset]
            asset_value += scaled_value
        return asset_value - self.debt

    def leverage_after_prices(self, prices: Dict[str, float], initial_prices: Dict[str, float]) -> float:
        eq = self.equity_after_prices(prices, initial_prices)
        asset_value = 0.0
        for asset, notional in self.exposures.items():
            asset_value += notional * prices[asset] / initial_prices[asset]
        if eq <= 0:
            return float("inf")
        return asset_value / eq

    def distressed(self, prices: Dict[str, float], initial_prices: Dict[str, float]) -> bool:
        return self.leverage_after_prices(prices, initial_prices) >= self.margin_threshold

    def liquidate(self, prices: Dict[str, float], initial_prices: Dict[str, float]) -> Dict[str, float]:
        # Sell a fixed fraction of current positions when distressed.
        sales = {}
        for asset, notional in self.exposures.items():
            sale_amount = notional * self.liquidation_fraction
            sales[asset] = sale_amount
            self.exposures[asset] -= sale_amount
        return sales


def build_system(seed: int = SEED) -> Tuple[List[Fund], Dict[str, float], Dict[str, float]]:
    random.seed(seed)

    assets = {
        "AERO": 100.0,
        "GRID": 100.0,
        "RAIL": 100.0,
        "CHIP": 100.0,
        "PORT": 100.0,
    }
    initial_prices = assets.copy()

    funds = [
        Fund("Atlas Capital", equity=100, leverage=3.8, margin_threshold=5.0, liquidation_fraction=0.22),
        Fund("North River", equity=90, leverage=4.1, margin_threshold=5.2, liquidation_fraction=0.25),
        Fund("Helix Partners", equity=110, leverage=3.4, margin_threshold=4.8, liquidation_fraction=0.20),
        Fund("Blue Harbor", equity=95, leverage=3.9, margin_threshold=5.1, liquidation_fraction=0.24),
        Fund("Summit Point", equity=105, leverage=3.5, margin_threshold=4.9, liquidation_fraction=0.21),
        Fund("Vector Ridge", equity=85, leverage=4.3, margin_threshold=5.4, liquidation_fraction=0.27),
    ]

    # Overlapping exposures generate spillovers.
    exposure_templates = [
        {"AERO": 0.30, "GRID": 0.25, "CHIP": 0.25, "PORT": 0.20},
        {"AERO": 0.20, "RAIL": 0.30, "GRID": 0.20, "PORT": 0.30},
        {"GRID": 0.35, "CHIP": 0.25, "PORT": 0.15, "RAIL": 0.25},
        {"AERO": 0.15, "CHIP": 0.35, "PORT": 0.30, "RAIL": 0.20},
        {"GRID": 0.25, "PORT": 0.25, "RAIL": 0.30, "AERO": 0.20},
        {"CHIP": 0.40, "PORT": 0.20, "AERO": 0.20, "GRID": 0.20},
    ]

    for fund, template in zip(funds, exposure_templates):
        gross_assets = fund.equity * fund.leverage
        exposures = {}
        for asset, weight in template.items():
            jitter = 1 + random.uniform(-0.05, 0.05)
            exposures[asset] = gross_assets * weight * jitter
        # Re-normalize.
        scale = gross_assets / sum(exposures.values())
        fund.exposures = {k: v * scale for k, v in exposures.items()}

    return funds, assets, initial_prices


def apply_price_impact(
    prices: Dict[str, float],
    aggregate_sales: Dict[str, float],
    depth: Dict[str, float],
    impact_alpha: float = 0.75,
) -> None:
    for asset, sale in aggregate_sales.items():
        if sale <= 0:
            continue
        impact = impact_alpha * (sale / depth[asset])
        # Exponential impact keeps prices positive while allowing nonlinearity.
        prices[asset] *= math.exp(-impact)
        prices[asset] = max(prices[asset], 5.0)


def run_single_scenario(initial_shock: float, shocked_asset: str = "CHIP") -> Dict[str, float]:
    funds, prices, initial_prices = build_system()
    depth = {asset: 950.0 for asset in prices.keys()}

    starting_system_equity = sum(fund.equity for fund in funds)
    prices[shocked_asset] *= (1 - initial_shock)

    distressed_names = set()
    rounds = 0

    while rounds < 12:
        rounds += 1
        aggregate_sales = {asset: 0.0 for asset in prices.keys()}
        newly_distressed = []

        for fund in funds:
            if fund.distressed(prices, initial_prices):
                newly_distressed.append(fund)

        if not newly_distressed:
            break

        for fund in newly_distressed:
            distressed_names.add(fund.name)
            sales = fund.liquidate(prices, initial_prices)
            for asset, amount in sales.items():
                aggregate_sales[asset] += amount

        apply_price_impact(prices, aggregate_sales, depth)

    ending_system_equity = sum(max(fund.equity_after_prices(prices, initial_prices), 0.0) for fund in funds)
    total_loss = max(starting_system_equity - ending_system_equity, 0.0)
    normalized_loss = total_loss / starting_system_equity

    return {
        "initial_shock": initial_shock,
        "system_loss": normalized_loss,
        "distressed_funds": float(len(distressed_names)),
        "rounds": float(rounds),
    }


def sweep_scenarios() -> List[Dict[str, float]]:
    shocks = [x / 100 for x in range(2, 31, 2)]
    results = [run_single_scenario(shock) for shock in shocks]
    return results


def create_system_loss_chart(results: List[Dict[str, float]]) -> None:
    x = [100 * r["initial_shock"] for r in results]
    y = [100 * r["system_loss"] for r in results]

    plt.figure(figsize=(8, 5))
    plt.plot(x, y, marker="o")
    plt.xlabel("Initial asset shock (%)")
    plt.ylabel("Final system equity loss (%)")
    plt.title("Shock size vs. system loss")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "system_loss_curve.png", dpi=180)
    plt.close()


def create_distress_chart(results: List[Dict[str, float]]) -> None:
    x = [100 * r["initial_shock"] for r in results]
    y = [r["distressed_funds"] for r in results]

    plt.figure(figsize=(8, 5))
    plt.plot(x, y, marker="o")
    plt.xlabel("Initial asset shock (%)")
    plt.ylabel("Distressed funds")
    plt.title("Shock size vs. number of distressed funds")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "cascade_count_curve.png", dpi=180)
    plt.close()


def create_network_snapshot(shock: float = 0.16) -> None:
    funds, prices, initial_prices = build_system()
    prices["CHIP"] *= (1 - shock)

    distressed = []
    for fund in funds:
        if fund.distressed(prices, initial_prices):
            distressed.append(fund.name)

    graph = nx.Graph()
    for fund in funds:
        graph.add_node(fund.name, node_type="fund")
        for asset, amount in fund.exposures.items():
            graph.add_node(asset, node_type="asset")
            graph.add_edge(fund.name, asset, weight=amount)

    pos = nx.spring_layout(graph, seed=SEED)
    fund_nodes = [n for n, d in graph.nodes(data=True) if d["node_type"] == "fund"]
    asset_nodes = [n for n, d in graph.nodes(data=True) if d["node_type"] == "asset"]

    fund_sizes = [1800 if n in distressed else 1200 for n in fund_nodes]
    edge_widths = [max(graph[u][v]["weight"] / 120, 0.8) for u, v in graph.edges()]

    plt.figure(figsize=(10, 7))
    nx.draw_networkx_nodes(graph, pos, nodelist=fund_nodes, node_size=fund_sizes)
    nx.draw_networkx_nodes(graph, pos, nodelist=asset_nodes, node_size=1000)
    nx.draw_networkx_edges(graph, pos, width=edge_widths, alpha=0.35)
    nx.draw_networkx_labels(graph, pos, font_size=9)
    plt.title("Fund-asset network after an initial CHIP shock")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "network_snapshot.png", dpi=180)
    plt.close()


def write_summary(results: List[Dict[str, float]]) -> None:
    # Find the first large jump in losses to highlight threshold behavior.
    threshold_text = "No obvious threshold detected."
    for prev, curr in zip(results[:-1], results[1:]):
        loss_jump = curr["system_loss"] - prev["system_loss"]
        distressed_jump = curr["distressed_funds"] - prev["distressed_funds"]
        if loss_jump > 0.06 or distressed_jump >= 2:
            threshold_text = (
                f"The first clear nonlinear jump appears between "
                f"{prev['initial_shock']*100:.0f}% and {curr['initial_shock']*100:.0f}% initial shock."
            )
            break

    lines = [
        "Volatility Cascade Engine — summary",
        "",
        "Key result:",
        threshold_text,
        "",
        "Scenario table:",
    ]
    for r in results:
        lines.append(
            f"- Shock {r['initial_shock']*100:>2.0f}% | "
            f"System loss {r['system_loss']*100:>5.1f}% | "
            f"Distressed funds {int(r['distressed_funds'])}"
        )

    (OUTPUT_DIR / "summary.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    results = sweep_scenarios()
    create_system_loss_chart(results)
    create_distress_chart(results)
    create_network_snapshot()
    write_summary(results)

    print("Generated outputs:")
    for path in sorted(OUTPUT_DIR.iterdir()):
        print(f"- {path.name}")


if __name__ == "__main__":
    main()