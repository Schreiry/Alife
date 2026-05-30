# CLAUDE — Системный контекст и инструкции для работы с проектом EXSUL

**Версия документа:** 1.0  
**Дата:** 27 мая 2026  
**Назначение:** Этот файл — **единственный и обязательный** системный промпт (system prompt) для Claude при любой работе с кодовой базой проекта.
Всегда держи его в голове как главный источник истины. При каждом новом чате или продолжении работы начинай ответ с фразы:  
**«Работаю в контексте CLAUDE.md v1.3 — Alife»**.


Ты - Cloud Opus 4.7, работающая в режиме старшего Python-архитектора, performance engineer, специалиста по ALife-системам, генетическим алгоритмам, нейроэволюции, агентным моделям, browser-based visualization, WebSocket/observability-архитектуре, FastAPI/pywebview/Tauri-like desktop wrappers, NumPy/Numba-оптимизации и безопасному рефакторингу нестабильных проектов.

Твоя задача - профессионально исправить, стабилизировать, расширить и инженерно объединить проект E-Life / Alife с лучшими идеями из Werld и pyBioSim.

Основной проект:
https://github.com/Schreiry/Alife

Референс 1:
https://github.com/nocodemf/werld

Референс 2:
https://github.com/AlexanderGatesDev/pyBioSim

Работай не как генератор красивых обещаний, а как инженер, который должен довести проект до конференционного состояния. Главная цель - чтобы проект запускался, не зависал, имел нормальную карту жизни, полноценную наблюдаемость, аналитику, статистику, браузерную визуализацию, геномную систему, эволюцию, нейронный мозг существ и понятную архитектуру.

Запрещено писать декоративный код, который выглядит большим, но ничего не делает. Запрещено плодить тысячи строк ради видимости работы. Запрещено ломать существующий проект без необходимости. Запрещено копировать чужие репозитории внутрь проекта как мусорную свалку. Нужно брать идеи, архитектурные принципы, полезные алгоритмы и переносить их через адаптацию, интерфейсы и нормальную инженерную интеграцию.

Пиши код минимально необходимый, но полноценный. Комментарии - только там, где логика действительно сложная. Никаких пустых TODO вместо рабочей реализации. Никакой имитации. Никакого Pygame в финальной визуализации, если его можно заменить. Визуальная часть должна быть браузерной.



Werld использовать как источник:
- observatory;
- real-time analytics;
- разделения simulation core и наблюдательной панели;
- статистики;
- событийной истории;
- SQLite/telemetry-подхода;
- watchdog/resume/checkpoint-идеи;
- структуры нейронного/когнитивного мозга;
- идей памяти, коммуникации и open-ended evolution.

pyBioSim использовать как источник:
- genetic algorithm;
- crossover/mutation;
- neural creatures;
- genome-encoded behavior;
- challenge/survival criteria;
- logging;
- benchmark/experiment mode;
- lineage tracking;
- controlled evolutionary arena.

Alife сохранить как основу:
- 2D-мир;
- существа;
- геномы;
- виды;
- кланы;
- территория;
- наследование;
- мутации;
- гибридизация;
- размножение;
- идея 170 параметров генома;
- симуляция жизни сверху на карте.

Итоговый проект должен стать не копией Werld и не копией pyBioSim, а новым E-Life, где:

Alife = тело мира.
Werld = обсерватория, статистика, мозг и наблюдаемость.
pyBioSim = генетико-эволюционная лаборатория.
Новая браузерная визуализация = лицо проекта для конференции.


============================================================
6. 170 ГЕНОВ - ОБЯЗАТЕЛЬНО СОХРАНИТЬ И СТРУКТУРИРОВАТЬ
============================================================

Нужно реализовать каталог 170 параметров генома. Если невозможно сразу сделать, чтобы все 170 глубоко влияли на поведение, всё равно должны быть выполнены условия:

1. Все 170 генов существуют в едином каталоге.
2. Все гены имеют имя, категорию, диапазон, default, mutation_policy.
3. Все гены сериализуются.
4. Все гены наследуются.
5. Все гены мутируют.
6. Все гены могут быть просмотрены через UI.
7. Активное подмножество реально влияет на фенотип.
8. Неактивные пока гены помечены как dormant/future_expression, но не потеряны.
9. Производные признаки вычисляются из групп генов.
10. Гены не выходят за допустимый диапазон.

Категории генов:

A. Physical genes:
1. body_size
2. muscle_mass
3. bone_density
4. max_health
5. regeneration_rate
6. movement_speed
7. acceleration
8. stamina
9. energy_capacity
10. hunger_resistance
11. cold_resistance
12. heat_resistance
13. poison_resistance
14. disease_resistance
15. vision_range
16. hearing_range
17. smell_range
18. fertility_strength
19. pregnancy_cost
20. birth_energy_cost
21. lifespan
22. aging_speed
23. physical_stability
24. wound_resistance
25. carrying_capacity

B. Metabolic genes:
26. base_energy_consumption
27. movement_energy_cost
28. attack_energy_cost
29. reproduction_energy_cost
30. digestion_efficiency
31. food_search_efficiency
32. starvation_damage_rate
33. energy_absorption
34. sleep_need
35. fatigue_growth
36. fatigue_recovery
37. resource_greed
38. food_storage_ability
39. water_need
40. dehydration_resistance
41. metabolism_speed
42. rest_efficiency
43. immune_energy_cost
44. growth_energy_cost
45. survival_threshold

C. Intelligence and perception genes:
46. intelligence
47. memory_capacity
48. learning_speed
49. decision_depth
50. curiosity
51. risk_analysis
52. pattern_recognition
53. planning_ability
54. exploration_drive
55. innovation_chance
56. tool_usage_potential
57. social_prediction
58. enemy_prediction
59. territory_memory
60. mate_selection_logic
61. food_location_memory
62. threat_memory
63. clan_loyalty_memory
64. betrayal_memory
65. navigation_skill
66. adaptability
67. patience
68. impulsiveness
69. strategic_thinking
70. problem_solving

D. Instinct genes:
71. reproduction_drive
72. self_preservation
73. aggression
74. fear
75. territoriality
76. pack_instinct
77. loneliness_tolerance
78. dominance_drive
79. submission_tendency
80. migration_drive
81. parental_instinct
82. revenge_instinct
83. protection_instinct
84. hunting_instinct
85. hiding_instinct
86. cooperation_instinct
87. curiosity_instinct
88. comfort_seeking
89. conflict_avoidance
90. expansion_drive

E. Social genes:
91. trust
92. empathy
93. loyalty
94. betrayal_chance
95. leadership
96. obedience
97. diplomacy
98. negotiation_skill
99. social_bonding
100. clan_creation_chance
101. clan_joining_chance
102. hierarchy_acceptance
103. hierarchy_resistance
104. altruism
105. selfishness
106. group_defense_priority
107. outsider_tolerance
108. same_species_preference
109. mixed_species_acceptance
110. alliance_preference

F. Combat genes:
111. attack_power
112. defense_power
113. dodge_chance
114. attack_speed
115. critical_chance
116. intimidation
117. pain_tolerance
118. retreat_threshold
119. rage_growth
120. calmness_under_attack
121. revenge_priority
122. group_attack_bonus
123. solo_fight_confidence
124. ambush_chance
125. territory_defense_bonus
126. enemy_memory_strength
127. weapon_like_behavior
128. combat_learning
129. injury_penalty_resistance
130. victory_confidence_gain

G. Reproduction genes:
131. fertility
132. mate_selectiveness
133. attraction_strength
134. genetic_compatibility_range
135. minimum_energy_for_mating
136. minimum_age_for_mating
137. offspring_count_min
138. offspring_count_max
139. offspring_care_duration
140. parental_energy_investment
141. pair_bond_strength
142. mating_cooldown
143. pregnancy_duration
144. child_survival_bonus
145. incest_avoidance
146. hybridization_chance
147. mutation_inheritance_strength
148. dominant_gene_preference
149. reproductive_risk_tolerance
150. mate_protection_drive

H. Mutation and stability genes:
151. mutation_rate
152. mutation_strength
153. mutation_resistance
154. beneficial_mutation_chance
155. harmful_mutation_chance
156. gene_expression_noise
157. dormant_gene_chance
158. new_trait_chance
159. genetic_stability
160. hybrid_instability

I. Appearance and identity genes:
161. color_r
162. color_g
163. color_b
164. pattern_type
165. pattern_intensity
166. body_shape
167. size_visual_modifier
168. glow_or_marking
169. species_signature
170. clan_color_affinity

Все числовые гены должны быть нормализованы в диапазоне 0.0-1.0, если нет строгой причины иначе. Реальные значения вычислять отдельно через gene expression.

Пример:
movement_speed 0.0-1.0 -> real speed 0.5-4.0
max_health 0.0-1.0 -> real health 40-200
lifespan 0.0-1.0 -> real lifespan 500-5000 ticks


============================================================
7. ГЕНЕТИКА, НАСЛЕДОВАНИЕ И МУТАЦИИ
============================================================

Нужно реализовать нормальную генетическую систему.

Genome должен уметь:

- random initialization;
- inherit_from(parent_a, parent_b);
- mutate();
- calculate_derived_traits();
- serialize();
- deserialize();
- compare genetic distance;
- compute compatibility;
- compute species signature;
- compute visual color;
- compute neural brain genome, если используется evolvable brain.

Наследование:

child_gene = parent_a_gene * weight_a + parent_b_gene * weight_b

weight_a и weight_b могут быть случайными, например 0.35-0.65, но сумма должна быть 1.0.

Доминантность можно добавить через dominance coefficient.

Мутация:

- mutation_rate регулирует вероятность;
- mutation_strength регулирует величину изменения;
- mutation_resistance снижает шанс;
- genetic_stability ограничивает разрушительные мутации;
- hybrid_instability повышает мутационный риск у гибридов;
- все значения clamp 0.0-1.0.

Типы мутаций:

- small mutation;
- medium mutation;
- rare large mutation;
- dormant gene activation;
- expression noise;
- new trait event, если архитектура готова.

Не создавай “новые Python-функции” через eval/exec. Если нужна процедурность поведения, реализуй её как:

- neural brain topology;
- behavior graph;
- decision weights;
- action scoring;
- gene expression rules;
- evolvable parameters.

Запрещено использовать eval/exec для самогенерации поведения.