Работаю в контексте CLAUDE.md v1.3 — Alife

# ALife — Документация проекта

**Технологии:**

- **Язык:** Python 3.11+ (основная кодовая база)
- **Платформа:** Browser-based observatory (FastAPI + WebSocket) и локальный GUI (pygame fallback)
- **Фреймворки / библиотеки:**
  - FastAPI, uvicorn (обсерватория / WebSocket сервер)
  - pygame-ce (локальная отладочная GUI отрисовка)
  - numpy (векторизованные расчёты, SoA-массивы)
  - numba (JIT для горячих кернелов, ускорение восприятия)
  - matplotlib (опционально для экспортируемых графиков в экспериментах)
  - прочие стандартные утилиты Python

**Кратко о проекте:**

ALife — двухмерная симуляция искусственной жизни. Существа имеют геном из 170 нормализованных генов, из которых вычисляются реальные фенотипические величины. Симуляция ориентирована на производительность: данные горячих полей хранятся в компактных numpy SoA-массивах, а критичные участки ускорены Numba и векторными операциями.

---

**Содержание документа:**

- **Обзор архитектуры** (компоненты и их связи)
- **Используемые технологии и оптимизации**
- **Как работает симуляция** (такт, подсистемы, поведение существ)
- **Генетическая система** (наследование, мутация, сигнатуры видов)
- **Каталог 170 генов** (полная таблица с объяснениями)
- **Графики и диаграммы** (включены SVG)
- **Рекомендации для разработки и расширения**

---

**1. Архитектура (высокоуровнево)**

Схема модулей (см. `docs/images/architecture.svg`): основные блоки — `core` (мир, сетки, драйвер тиков), `genetics` (каталог генов, геном, наследование, мутация), `entities` (существо, клан, ресурсы), `behavior` (восприятие, принятие решений, бои, размножение), `rendering`/`frontend` (отрисовка, observatory) и `data` (логирование, сохранение, статистика).

- Точка входа: `main.py` — выбирает режим запуска: observatory (FastAPI + браузер), gui (pygame), headless/experiments.
- Драйвер симуляции: `core.simulation.Simulation` — управляет циклом тик→обновления→рендер.
- Представление мира: `core.world.World` + spatial grids — spatial hash / counting-sort индекс для быстрых запросов соседей.
- Горячие поля: `CreatureStore` — SoA numpy-массивы для позиций, энергии, здоровья и кэшированных фенотипов.
- Поведение: `behavior.brain` делает per-creature step, вызывает perception → decisions → action handlers.
- Генетика: `genetics.genome.Genome` + `genetics.genes.GENE_CATALOG` + `genetics.inheritance`, `genetics.mutation`.

**2. Используемые технологии и почему**

- Python — простота разработки и богатая экосистема численных библиотек.
- Numpy — эффективная обработка больших массивов (SoA), векторизация массовых операций.
- Numba — JIT ускорение горячих алгоритмов (восприятие, spatial kernels).
- FastAPI + WebSocket — браузерная обсерватория, асинхронный сервер для отправки снимков мира и событий.
- Pygame-ce — удобный локальный рендер/debug режим.

**3. Оптимизации, реализованные в проекте**

- Data-oriented design: горячие данные в плотных numpy-массивах (SoA), минимизация Python-оберток на горячем пути.
- Spatial index: counting-sort style spatial grid: rebuild O(N) и быстрый query возвращающий numpy-массив индексов.
- Vectorized passive updates: массовые операции возраста, энергии, старения и регенерации делаются едиными numpy-выражениями.
- Numba кернелы: горячие части восприятия/соседей JIT-компилируются.
- Throttling: дорогие подсистемы выполняются по интервалам из `config.py`.

**4. Принцип работы симуляции (один тик)**

1. Экология: регенерация биомассы по зонам, затем спавн еды.
2. Векторные пассивные обновления: возраст, расход энергии, старение, регенерация.
3. Удаление павших.
4. Перестройка spatial grids.
5. Brain pass: perceive → score_actions → handler.
6. Throttled subsystems: diplomacy, territory decay, species resync.
7. Сбор статистики и телеметрии.

**5. Генетическая система: общие принципы**

- `Genome` — numpy-массив длины 170, значения 0.0–1.0.
- `genes.real_value()` конвертирует нормализованные значения в реальные диапазоны.
- Наследование: пер-генийный взвешенный кроссовер; мутации применяются inplace с учётом `mutation_rate` и `mutation_strength`.

---

**6. Каталог 170 генов**

Ниже — полная таблица всех 170 генов: индекс, имя, категория, реальный диапазон и краткая роль. Все значения нормализованы в хранилище; реальные значения вычисляются по необходимости.

| # | Имя | Категория | Реальный диапазон | Краткая роль |
|---:|---|---|---|---|

<!-- A. Physical (1-25) -->
| 1 | body_size | physical | 0.4–2.0 | Размер тела — влияет на визуал, инерцию и некоторые физические взаимодействия. |
| 2 | muscle_mass | physical | 0.3–2.0 | Сила: масштабирует физическую силу и эффективность атаки/перемещения. |
| 3 | bone_density | physical | 0.3–1.5 | Снижение урона от травм, устойчивость к повреждениям. |
| 4 | max_health | physical | 40–200 | Максимум здоровья. |
| 5 | regeneration_rate | physical | 0.0–0.6 | Скорость восстановления здоровья. |
| 6 | movement_speed | physical | 0.5–4.0 | Базовая скорость передвижения. |
| 7 | acceleration | physical | 0.2–1.5 | Как быстро достигается скорость после начала движения. |
| 8 | stamina | physical | 20–200 | Выносливость для интенсивной активности. |
| 9 | energy_capacity | physical | 60–240 | Максимальная энергия для действий. |
|10 | hunger_resistance | physical | 0.0–1.0 | Уменьшает негатив от голода. |
|11 | cold_resistance | physical | 0.0–1.0 | Устойчивость к холоду (для биомов). |
|12 | heat_resistance | physical | 0.0–1.0 | Устойчивость к жаре (для биомов). |
|13 | poison_resistance | physical | 0.0–1.0 | Снижение эффектов от токсинов. |
|14 | disease_resistance | physical | 0.0–1.0 | Сопротивление болезням. |
|15 | vision_range | physical | 4.0–18.0 | Радиус зрения: дальность восприятия объектов. |
|16 | hearing_range | physical | 2.0–16.0 | Радиус слуха. |
|17 | smell_range | physical | 2.0–14.0 | Радиус обоняния/поиска пищи вне LOS. |
|18 | fertility_strength | physical | 0.1–1.0 | Базовая фертильность. |
|19 | pregnancy_cost | physical | 0.1–0.5 | Энергетический коэффициент беременности. |
|20 | birth_energy_cost | physical | 10–60 | Стоимость родов в энергии. |
|21 | lifespan | physical | 500–5000 | Длительность жизни в тиках. |
|22 | aging_speed | physical | 0.5–2.0 | Скорость старения. |
|23 | physical_stability | physical | 0.0–1.0 | Сопротивление нестабильности/падениям. |
|24 | wound_resistance | physical | 0.0–1.0 | Снижение урона от ран. |
|25 | carrying_capacity | physical | 0.0–10.0 | Грузоподъёмность/ёмкость ресурсов. |

<!-- B. Metabolic (26-45) -->
|26 | base_energy_consumption | metabolic | 0.02–0.20 | Базовый расход энергии в покое. |
|27 | movement_energy_cost | metabolic | 0.02–0.30 | Стоимость передвижения на единицу. |
|28 | attack_energy_cost | metabolic | 0.5–3.0 | Энергия для атаки. |
|29 | reproduction_energy_cost | metabolic | 10–80 | Энергия, требуемая для размножения. |
|30 | digestion_efficiency | metabolic | 0.4–1.4 | Эффективность превращения пищи в энергию. |
|31 | food_search_efficiency | metabolic | 0.0–1.0 | Эффективность поиска пищи. |
|32 | starvation_damage_rate | metabolic | 0.2–1.5 | Урон при голоде. |
|33 | energy_absorption | metabolic | 0.5–1.6 | Модификатор усвоения энергии от еды. |
|34 | sleep_need | metabolic | 0.0–1.0 | Потребность в отдыхе. |
|35 | fatigue_growth | metabolic | 0.0–1.0 | Нарастание усталости. |
|36 | fatigue_recovery | metabolic | 0.0–1.0 | Восстановление от усталости. |
|37 | resource_greed | metabolic | 0.0–1.0 | Склонность аккумулировать ресурсы. |
|38 | food_storage_ability | metabolic | 0.0–1.0 | Возможность хранить пищу. |
|39 | water_need | metabolic | 0.0–1.0 | Потребность во влаге. |
|40 | dehydration_resistance | metabolic | 0.0–1.0 | Устойчивость к обезвоживанию. |
|41 | metabolism_speed | metabolic | 0.5–1.8 | Скорость метаболизма. |
|42 | rest_efficiency | metabolic | 0.0–1.0 | Эффективность отдыха. |
|43 | immune_energy_cost | metabolic | 0.0–1.0 | Энергетическая цена иммунного ответа. |
|44 | growth_energy_cost | metabolic | 0.0–1.0 | Стоимость роста. |
|45 | survival_threshold | metabolic | 0.05–0.4 | Пороговое значение выживаемости/стратегии. |

<!-- C. Intelligence / perception (46-70) -->
|46 | intelligence | intellect | 0.0–1.0 | Общая когнитивная способность. |
|47 | memory_capacity | intellect | 0.0–1.0 | Ёмкость локальной памяти. |
|48 | learning_speed | intellect | 0.0–1.0 | Скорость обучения. |
|49 | decision_depth | intellect | 0.0–1.0 | Глубина планирования. |
|50 | curiosity | intellect | 0.0–1.0 | Склонность к исследованию. |
|51 | risk_analysis | intellect | 0.0–1.0 | Оценка рисков. |
|52 | pattern_recognition | intellect | 0.0–1.0 | Распознавание паттернов. |
|53 | planning_ability | intellect | 0.0–1.0 | Способность строить планы. |
|54 | exploration_drive | intellect | 0.0–1.0 | Движение к новым территориям. |
|55 | innovation_chance | intellect | 0.0–1.0 | Вероятность экспериментальных действий. |
|56 | tool_usage_potential | intellect | 0.0–1.0 | Потенциал использования предметов. |
|57 | social_prediction | intellect | 0.0–1.0 | Прогнозирование поведения других. |
|58 | enemy_prediction | intellect | 0.0–1.0 | Прогнозирование врагов. |
|59 | territory_memory | intellect | 0.0–1.0 | Память о границах/территории. |
|60 | mate_selection_logic | intellect | 0.0–1.0 | Логика выбора партнёра. |
|61 | food_location_memory | intellect | 0.0–1.0 | Память мест с едой. |
|62 | threat_memory | intellect | 0.0–1.0 | Память о угрозах. |
|63 | clan_loyalty_memory | intellect | 0.0–1.0 | Память о лояльности к клану. |
|64 | betrayal_memory | intellect | 0.0–1.0 | Память о предательствах. |
|65 | navigation_skill | intellect | 0.0–1.0 | Навигационные умения. |
|66 | adaptability | intellect | 0.0–1.0 | Приспосабливаемость. |
|67 | patience | intellect | 0.0–1.0 | Терпение/удержание цели. |
|68 | impulsiveness | intellect | 0.0–1.0 | Склонность к спонтанным решениям. |
|69 | strategic_thinking | intellect | 0.0–1.0 | Стратегическое мышление. |
|70 | problem_solving | intellect | 0.0–1.0 | Решение локальных задач. |

<!-- D. Instincts (71-90) -->
|71 | reproduction_drive | instinct | 0.0–1.0 | Желание размножаться. |
|72 | self_preservation | instinct | 0.0–1.0 | Инстинкт самосохранения. |
|73 | aggression | instinct | 0.0–1.0 | Агрессия. |
|74 | fear | instinct | 0.0–1.0 | Страх/бегство. |
|75 | territoriality | instinct | 0.0–1.0 | Защита территории. |
|76 | pack_instinct | instinct | 0.0–1.0 | Склонность к группе. |
|77 | loneliness_tolerance | instinct | 0.0–1.0 | Терпимость к одиночеству. |
|78 | dominance_drive | instinct | 0.0–1.0 | Желание доминировать. |
|79 | submission_tendency | instinct | 0.0–1.0 | Склонность к подчинению. |
|80 | migration_drive | instinct | 0.0–1.0 | Склонность к миграции. |
|81 | parental_instinct | instinct | 0.0–1.0 | Забота о потомстве. |
|82 | revenge_instinct | instinct | 0.0–1.0 | Тенденция к мести. |
|83 | protection_instinct | instinct | 0.0–1.0 | Желание защищать союзников. |
|84 | hunting_instinct | instinct | 0.0–1.0 | Склонность к охоте. |
|85 | hiding_instinct | instinct | 0.0–1.0 | Склонность прятаться. |
|86 | cooperation_instinct | instinct | 0.0–1.0 | Склонность сотрудничать. |
|87 | curiosity_instinct | instinct | 0.0–1.0 | Инстинктивное любопытство. |
|88 | comfort_seeking | instinct | 0.0–1.0 | Поиск комфортных зон. |
|89 | conflict_avoidance | instinct | 0.0–1.0 | Избегание конфликтов. |
|90 | expansion_drive | instinct | 0.0–1.0 | Желание расширять владения. |

<!-- E. Social (91-110) -->
|91 | trust | social | 0.0–1.0 | Доверие к другим. |
|92 | empathy | social | 0.0–1.0 | Эмпатия и помощь. |
|93 | loyalty | social | 0.0–1.0 | Лояльность к группе. |
|94 | betrayal_chance | social | 0.0–1.0 | Риск предательства. |
|95 | leadership | social | 0.0–1.0 | Склонность лидировать. |
|96 | obedience | social | 0.0–1.0 | Склонность подчиняться. |
|97 | diplomacy | social | 0.0–1.0 | Дипломатические навыки. |
|98 | negotiation_skill | social | 0.0–1.0 | Навык переговоров. |
|99 | social_bonding | social | 0.0–1.0 | Формирование связей. |
|100| clan_creation_chance | social | 0.0–1.0 | Шанс основать клан. |
|101| clan_joining_chance | social | 0.0–1.0 | Склонность вступать в клан. |
|102| hierarchy_acceptance | social | 0.0–1.0 | Приём иерархий. |
|103| hierarchy_resistance | social | 0.0–1.0 | Сопротивление иерархиям. |
|104| altruism | social | 0.0–1.0 | Альтруизм. |
|105| selfishness | social | 0.0–1.0 | Эгоизм. |
|106| group_defense_priority | social | 0.0–1.0 | Приоритет групповой обороны. |
|107| outsider_tolerance | social | 0.0–1.0 | Толерантность к чужакам. |
|108| same_species_preference | social | 0.0–1.0 | Предпочтение своего вида. |
|109| mixed_species_acceptance | social | 0.0–1.0 | Прием межвидовых союзов. |
|110| alliance_preference | social | 0.0–1.0 | Склонность к альянсам. |

<!-- F. Combat (111-130) -->
|111| attack_power | combat | 2.0–30.0 | Базовая сила атаки. |
|112| defense_power | combat | 0.0–20.0 | Базовая защита. |
|113| dodge_chance | combat | 0.0–0.5 | Шанс увернуться. |
|114| attack_speed | combat | 0.5–2.0 | Частота атак. |
|115| critical_chance | combat | 0.0–0.3 | Шанс крита. |
|116| intimidation | combat | 0.0–1.0 | Запугивание. |
|117| pain_tolerance | combat | 0.0–1.0 | Работа при боли. |
|118| retreat_threshold | combat | 0.05–0.6 | Порог для отступления. |
|119| rage_growth | combat | 0.0–1.0 | Нарастание ярости. |
|120| calmness_under_attack | combat | 0.0–1.0 | Удержание контроля. |
|121| revenge_priority | combat | 0.0–1.0 | Приоритет мести. |
|122| group_attack_bonus | combat | 0.0–1.0 | Бонус групповых атак. |
|123| solo_fight_confidence | combat | 0.0–1.0 | Уверенность в одиночке. |
|124| ambush_chance | combat | 0.0–0.5 | Попытка засады. |
|125| territory_defense_bonus | combat | 0.0–1.0 | Бонус на своей территории. |
|126| enemy_memory_strength | combat | 0.0–1.0 | Запоминание врагов. |
|127| weapon_like_behavior | combat | 0.0–1.0 | Использование предметов в бою. |
|128| combat_learning | combat | 0.0–1.0 | Обучение боям. |
|129| injury_penalty_resistance | combat | 0.0–1.0 | Сопротивление штрафам от травм. |
|130| victory_confidence_gain | combat | 0.0–0.4 | Уверенность после победы. |

<!-- G. Reproduction (131-150) -->
|131| fertility | reproduction | 0.1–1.0 | Фертильность и здоровье потомства. |
|132| mate_selectiveness | reproduction | 0.0–1.0 | Разборчивость в партнёрах. |
|133| attraction_strength | reproduction | 0.0–1.0 | Привлекательность для партнёров. |
|134| genetic_compatibility_range | reproduction | 0.1–1.0 | Порог генетической совместимости. |
|135| minimum_energy_for_mating | reproduction | 0.25–0.55 | Мин. доля энергии для допуска к спариванию. |
|136| minimum_age_for_mating | reproduction | 30–150 | Мин. возраст для размножения. |
|137| offspring_count_min | reproduction | 1.0–3.0 | Мин. число отпрысков. |
|138| offspring_count_max | reproduction | 1.0–5.0 | Макс. число отпрысков. |
|139| offspring_care_duration | reproduction | 0.0–200.0 | Длительность ухода за потомством. |
|140| parental_energy_investment | reproduction | 0.0–0.5 | Энергетические вложения в потомство. |
|141| pair_bond_strength | reproduction | 0.0–1.0 | Сила парной связи. |
|142| mating_cooldown | reproduction | 40–160 | Интервал между спариваниями. |
|143| pregnancy_duration | reproduction | 30–150 | Длительность беременности. |
|144| child_survival_bonus | reproduction | 0.0–1.0 | Бонус к выживанию детей. |
|145| incest_avoidance | reproduction | 0.0–1.0 | Избегание инцеста. |
|146| hybridization_chance | reproduction | 0.0–1.0 | Шанс гибридизации. |
|147| mutation_inheritance_strength | reproduction | 0.0–1.0 | Наследуемость новых мутаций. |
|148| dominant_gene_preference | reproduction | 0.0–1.0 | Смещение в сторону доминантных аллелей. |
|149| reproductive_risk_tolerance | reproduction | 0.0–1.0 | Готовность идти на риски при размножении. |
|150| mate_protection_drive | reproduction | 0.0–1.0 | Защитное поведение при размножении. |

<!-- H. Mutation / stability (151-160) -->
|151| mutation_rate | mutation | 0.005–0.20 | Базовая вероятность мутации. |
|152| mutation_strength | mutation | 0.01–0.25 | Сила изменения при мутации. |
|153| mutation_resistance | mutation | 0.0–1.0 | Уменьшает шанс мутации. |
|154| beneficial_mutation_chance | mutation | 0.0–1.0 | Шанс полезной мутации. |
|155| harmful_mutation_chance | mutation | 0.0–1.0 | Шанс вредной мутации. |
|156| gene_expression_noise | mutation | 0.0–1.0 | Шум в реализации генов. |
|157| dormant_gene_chance | mutation | 0.0–1.0 | Шанс активации дремлющих генов. |
|158| new_trait_chance | mutation | 0.0–1.0 | Редкая генерация новой черты. |
|159| genetic_stability | mutation | 0.0–1.0 | Общая стабильность генома. |
|160| hybrid_instability | mutation | 0.0–1.0 | Нестабильность гибридов (увелич. мутаций). |

<!-- I. Appearance / identity (161-170) -->
|161| color_r | appearance | 0.0–1.0 | Красная компонент цвета. |
|162| color_g | appearance | 0.0–1.0 | Зелёная компонент цвета. |
|163| color_b | appearance | 0.0–1.0 | Синяя компонент цвета. |
|164| pattern_type | appearance | 0.0–1.0 | Тип/категория узора. |
|165| pattern_intensity | appearance | 0.0–1.0 | Интенсивность узора. |
|166| body_shape | appearance | 0.0–1.0 | Визуальная форма тела. |
|167| size_visual_modifier | appearance | 0.6–1.6 | Визуальный множитель размера. |
|168| glow_or_marking | appearance | 0.0–1.0 | Наличие свечения/маркировок. |
|169| species_signature | appearance | 0.0–1.0 | Маркер вида для группировки/цвета. |
|170| clan_color_affinity | appearance | 0.0–1.0 | Склонность принимать цвета клана. |

---

Файл документации создан: [docs/ALIFE_DOCUMENTATION.md](docs/ALIFE_DOCUMENTATION.md)
