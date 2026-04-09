"""
Indicators component — technical indicator selection, configuration, and display.
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, List

from app.services.indicator_service import IndicatorService, INDICATOR_REGISTRY


def indicator_component():
    """Render the indicators page."""
    st.header("技术指标")

    svc = IndicatorService()

    # ---- Sidebar: indicator selection ----
    with st.sidebar:
        st.markdown("### 指标设置")

        # Category filter
        all_indicators = svc.list_indicators()
        categories = sorted(set(ind["category"] for ind in all_indicators))
        selected_category = st.selectbox("指标类别", ["全部"] + categories)

        # Filter indicators
        if selected_category == "全部":
            filtered = all_indicators
        else:
            filtered = [ind for ind in all_indicators if ind["category"] == selected_category]

        # Indicator selection
        indicator_names = [ind["display_name"] for ind in filtered]
        name_to_key = {ind["display_name"]: ind["name"] for ind in filtered}

        selected_display = st.selectbox("选择指标", indicator_names)
        indicator_key = name_to_key.get(selected_display)

        # Parameter configuration
        params: Dict[str, Any] = {}
        if indicator_key and indicator_key in INDICATOR_REGISTRY:
            default_params = INDICATOR_REGISTRY[indicator_key]["default_params"]
            for pname, pval in default_params.items():
                if isinstance(pval, int):
                    params[pname] = st.number_input(
                        pname, value=pval, min_value=1, step=1,
                    )
                elif isinstance(pval, float):
                    params[pname] = st.number_input(
                        pname, value=pval, min_value=0.1, step=0.1, format="%.1f",
                    )

        # Data source (symbol + date range)
        symbol = st.text_input("股票代码", value="600519", key="ind_symbol")
        col1, col2 = st.columns(2)
        with col1:
            ind_start = st.date_input("开始日期", value=pd.Timestamp("2024-01-01"), key="ind_start")
        with col2:
            ind_end = st.date_input("结束日期", value=pd.Timestamp("2024-12-31"), key="ind_end")

        calculate_btn = st.button("计算指标", use_container_width=True, type="primary")

    # ---- Main content ----
    if not indicator_key:
        st.info("请从左侧选择一个技术指标。")
        return

    # Show indicator description
    info = svc.get_indicator_info(indicator_key)
    if info:
        st.subheader(f"{info['display_name']}")
        st.caption(f"类别: {info['category']} | 内置: {'是' if info['is_builtin'] else '否'}")

    # Trigger calculation
    if calculate_btn or st.session_state.get("indicator_result") is not None:
        if calculate_btn:
            with st.spinner("正在获取数据并计算指标..."):
                try:
                    from app.services.data_service import DataService
                    data_svc = DataService()
                    df = data_svc.get_history(
                        symbols=[symbol],
                        start_date=str(ind_start),
                        end_date=str(ind_end),
                        period="1d",
                        dividend_type="front",
                    )
                    data_svc.close()
                    if df.empty:
                        st.warning("未获取到数据。")
                        return
                    results = svc.calculate(indicator_key, df, params=params)
                    st.session_state.indicator_result = results
                    st.session_state.indicator_df = df
                except Exception as e:
                    st.error(f"计算失败: {e}")
                    return

        results = st.session_state.get("indicator_result")
        df = st.session_state.get("indicator_df")

        if results is None or df is None:
            st.info("请点击「计算指标」开始。")
            return

        # Display results
        for name, series in results.items():
            with st.expander(f"📊 {name}", expanded=True):
                # Statistics
                col1, col2, col3, col4 = st.columns(4)
                valid = series.dropna()
                with col1:
                    st.metric("最新值", f"{valid.iloc[-1]:.4f}" if len(valid) > 0 else "N/A")
                with col2:
                    st.metric("最大值", f"{valid.max():.4f}" if len(valid) > 0 else "N/A")
                with col3:
                    st.metric("最小值", f"{valid.min():.4f}" if len(valid) > 0 else "N/A")
                with col4:
                    st.metric("均值", f"{valid.mean():.4f}" if len(valid) > 0 else "N/A")

                # Simple chart
                import plotly.graph_objects as go
                x = df["date"] if "date" in df.columns else df.index
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=x, y=series, mode="lines", name=name))
                fig.update_layout(
                    title=name,
                    template="plotly_white",
                    height=300,
                    margin={"l": 60, "r": 30, "t": 40, "b": 50},
                )
                st.plotly_chart(fig, use_container_width=True)

        # Overlay on price chart
        with st.expander("叠加到K线图"):
            from app.services.visualization_service import create_candlestick
            fig = create_candlestick(df, title=f"{symbol} + {selected_display}", show_volume=True)
            try:
                svc.add_indicator_to_figure(fig, indicator_key, df, params=params)
            except Exception as e:
                st.warning(f"叠加失败: {e}")
            st.plotly_chart(fig, use_container_width=True)
