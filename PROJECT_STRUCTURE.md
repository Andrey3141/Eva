# PROJECT_STRUCTURE.md

```
eva/
├── .env
├── .env.example
├── .pytest_cache/
│   ├── CACHEDIR.TAG
│   ├── README.md
│   └── v/
│       └── cache/
│           ├── lastfailed
│           └── nodeids
├── EVA.spec
├── PROJECT_STRUCTURE.md
├── assets/
│   ├── avatar/
│   │   ├── preview.mp4
│   │   ├── speaks.mp4
│   │   ├── thinks.mp4
│   │   └── warp.mp4
│   └── silero/
│       └── v4_ru.pt
├── assistant/
│   ├── __init__.py
│   ├── actions/
│   │   ├── actions_impl.py
│   │   ├── base.py
│   │   ├── validators.py
│   │   └── window_control.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── aec.py
│   │   ├── device.py
│   │   ├── listener.py
│   │   ├── playback.py
│   │   ├── player.py
│   │   ├── recorder.py
│   │   └── stream.py
│   ├── confirmation/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── keyword_parser.py
│   ├── core.py
│   ├── events/
│   │   ├── __init__.py
│   │   ├── bus.py
│   │   └── events.py
│   ├── gradebook/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── excel_gradebook.py
│   ├── intent/
│   │   ├── base.py
│   │   ├── echo_intent_parser.py
│   │   ├── llm_intent_parser.py
│   │   ├── parameter/
│   │   │   ├── __init__.py
│   │   │   ├── candidate_generator.py
│   │   │   ├── dataset.py
│   │   │   ├── embedding_candidate_scorer.py
│   │   │   ├── facade.py
│   │   │   ├── fusion.py
│   │   │   ├── ml_slot_tagger.py
│   │   │   ├── parameter_extractor.py
│   │   │   ├── roles.py
│   │   │   ├── router.py
│   │   │   └── types.py
│   │   └── router/
│   │       ├── __init__.py
│   │       ├── dataset.py
│   │       ├── embedding_router.py
│   │       ├── fusion.py
│   │       ├── llm_router.py
│   │       ├── ml_classifier.py
│   │       ├── parameter_extractor.py
│   │       ├── providers.py
│   │       ├── router.py
│   │       └── types.py
│   ├── llm/
│   │   ├── base.py
│   │   ├── cerebras_provider.py
│   │   ├── deepseek_llm.py
│   │   ├── echo_llm.py
│   │   ├── gemini_provider.py
│   │   ├── groq_provider.py
│   │   ├── openrouter_provider.py
│   │   └── router/
│   │       ├── __init__.py
│   │       ├── network.py
│   │       ├── provider_config.py
│   │       ├── router.py
│   │       └── state.py
│   ├── logging_setup.py
│   ├── paths.py
│   ├── response/
│   │   ├── base.py
│   │   ├── echo_response.py
│   │   └── llm_response.py
│   ├── stt/
│   │   ├── base.py
│   │   └── whisper_stt.py
│   ├── tts/
│   │   ├── base.py
│   │   ├── edge_tts.py
│   │   ├── fallback_tts.py
│   │   ├── pyttsx3_tts.py
│   │   └── silero_tts.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── animations.py
│   │   ├── app.py
│   │   ├── avatar/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── gif_renderer.py
│   │   │   ├── image_renderer.py
│   │   │   ├── registry.py
│   │   │   └── video_renderer.py
│   │   ├── avatar_view.py
│   │   ├── chat_view.py
│   │   ├── intro_view.py
│   │   ├── log_view.py
│   │   ├── main_window.py
│   │   ├── scene_container.py
│   │   ├── settings_store.py
│   │   ├── settings_view.py
│   │   ├── sidebar.py
│   │   ├── state_manager.py
│   │   └── theme.py
│   └── wake/
│       ├── base.py
│       └── keyword_detector.py
├── config.py
├── data/
│   ├── _test_gradebook_d.xlsx
│   ├── intent_examples.json
│   ├── parameter_examples.json
│   └── test_gradebook.xlsx
├── logs/
├── main.py
├── pyproject.toml
├── requirements.txt
├── script.py
├── tools/
│   ├── audit_project.py
│   ├── debug_render.py
│   ├── debug_video_geometry.py
│   ├── inspect_gradebook.py
│   ├── inspect_real_gradebook.py
│   ├── make_placeholder_avatar.py
│   ├── make_test_gradebook.py
│   ├── test_actions.py
│   ├── test_aec.py
│   ├── test_app_integration.py
│   ├── test_atomic_save.py
│   ├── test_avatar_gif_loop.py
│   ├── test_avatar_video_states.py
│   ├── test_cerebras_provider.py
│   ├── test_close_restart_actions.py
│   ├── test_config.py
│   ├── test_confirmation_flow.py
│   ├── test_confirmation_parser.py
│   ├── test_core.py
│   ├── test_embedding_candidate_scorer.py
│   ├── test_embedding_router.py
│   ├── test_event_bus.py
│   ├── test_fastembed_provider.py
│   ├── test_gemini_provider.py
│   ├── test_grade_student_parameter_router.py
│   ├── test_gradebook.py
│   ├── test_groq_provider.py
│   ├── test_gui_log_handler.py
│   ├── test_integration_pipeline.py
│   ├── test_intent.py
│   ├── test_intent_fusion.py
│   ├── test_intent_router.py
│   ├── test_intent_router_dataset.py
│   ├── test_intent_router_integration.py
│   ├── test_intent_router_parameter_integration.py
│   ├── test_intent_router_scenarios.py
│   ├── test_intent_routing_close_restart.py
│   ├── test_intro_view.py
│   ├── test_kastyli_parameter_router.py
│   ├── test_llm_intent_router.py
│   ├── test_llm_router.py
│   ├── test_logging_setup.py
│   ├── test_ml_classifier.py
│   ├── test_open_presentation_action.py
│   ├── test_open_video_pipeline.py
│   ├── test_parameter_extractor.py
│   ├── test_parameter_facade_mode.py
│   ├── test_parameter_router.py
│   ├── test_paths.py
│   ├── test_pipeline_params_to_action.py
│   ├── test_presentation_topic_bounds.py
│   ├── test_presentations_dir.py
│   ├── test_response.py
│   ├── test_runtime_apply.py
│   ├── test_settings_full_audit.py
│   ├── test_settings_store.py
│   ├── test_smoke_startup.py
│   ├── test_tts.py
│   ├── test_validators.py
│   ├── test_wake.py
│   ├── test_wake_aliases.py
│   ├── test_whisper_startup.py
│   └── test_whisper_stt.py
├── xnaskjdnliaewb
├── блендер/
│   ├── Alesya/
│   │   ├── accessories/
│   │   │   ├── __init__.py
│   │   │   ├── flowers.py
│   │   │   ├── hat.py
│   │   │   ├── ornament.py
│   │   │   └── ribbon.py
│   │   ├── animation/
│   │   │   ├── __init__.py
│   │   │   ├── eyes.py
│   │   │   ├── face.py
│   │   │   ├── idle.py
│   │   │   └── mouth.py
│   │   ├── build.py
│   │   ├── character/
│   │   │   ├── __init__.py
│   │   │   ├── body.py
│   │   │   ├── clothes.py
│   │   │   ├── eyes.py
│   │   │   ├── face.py
│   │   │   ├── hair.py
│   │   │   ├── head.py
│   │   │   ├── head_adaptation.py
│   │   │   └── head_work.py
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── materials.py
│   │   ├── scene/
│   │   │   ├── __init__.py
│   │   │   ├── camera.py
│   │   │   └── lighting.py
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── test_external_objects.py
│   │   │   ├── test_eyes.py
│   │   │   ├── test_eyes_visual.py
│   │   │   ├── test_face_anthropometry.py
│   │   │   ├── test_head.py
│   │   │   ├── test_head_adaptation.py
│   │   │   ├── test_head_adaptation_visual_debug.py
│   │   │   ├── test_head_base_external.py
│   │   │   ├── test_head_visual.py
│   │   │   ├── test_head_work_copy.py
│   │   │   └── test_output/
│   │   │       ├── eyes_test_front.png
│   │   │       ├── eyes_visual_diagnostic.png
│   │   │       ├── face_anthropometry_landmarks.png
│   │   │       ├── head_test_3q.png
│   │   │       ├── head_test_front.png
│   │   │       ├── head_test_profile.png
│   │   │       ├── head_test_report.txt
│   │   │       ├── head_test_top.png
│   │   │       ├── head_visual_3q.png
│   │   │       ├── head_visual_front.png
│   │   │       ├── head_visual_profile.png
│   │   │       └── head_visual_top.png
│   │   ├── utils.py
│   │   └── xnaskjdnliaewb
│   ├── human-base-meshes-bundle-v1.4.1/
│   │   ├── blender_assets.cats.txt
│   │   ├── blender_assets.cats.txt~
│   │   ├── human_base_meshes_bundle.blend
│   │   ├── human_base_meshes_bundle.blend1
│   │   └── thumbnails/
│   │       ├── planar_head.png
│   │       ├── planar_skull.png
│   │       ├── primitive_body_female_realistic.png
│   │       ├── primitive_body_female_stylized.png
│   │       ├── primitive_body_male_realistic.png
│   │       ├── primitive_body_male_stylized.png
│   │       ├── primitive_head_generic.png
│   │       ├── primitive_head_realistic.png
│   │       ├── realistic_body_female.png
│   │       ├── realistic_body_male.png
│   │       ├── realistic_eye.png
│   │       ├── realistic_foot.png
│   │       ├── realistic_hand.png
│   │       ├── realistic_head_anim.png
│   │       ├── realistic_head_sculpt.png
│   │       ├── realistic_jaw.png
│   │       ├── realistic_skeleton.png
│   │       ├── realistic_skull.png
│   │       ├── stylized_body_female.png
│   │       ├── stylized_body_male.png
│   │       ├── stylized_eye.png
│   │       ├── stylized_foot.png
│   │       ├── stylized_hand.png
│   │       ├── stylized_head.png
│   │       └── stylized_jaw.png
│   ├── алеся.blend
│   └── алеся.blend1
├── видео/
│   ├── frame_100.jpg
│   ├── main.py
│   ├── видео/
│   │   ├── 1-3.mp4
│   │   ├── gif.mp4
│   │   └── merged.mp4
│   └── кадры/
│       └── frame_302.jpg
└── кастыли/
    ├── __init__.py
    ├── grade.py
    ├── presentation.py
    ├── router.py
    └── video.py
```
